// Session-local NX Open dispatcher for the Online Machining project.
//
// NX loads this assembly at start-up from the `startup` folder of the custom
// directory named in UGII_CUSTOM_DIRECTORY_FILE and calls `ufsta`. NX accepts
// that entry point only with an int or string return type; a void one is
// rejected with "return type is not an integer or string". The dispatcher then
// polls a queue on a Windows message-loop timer, so every NX API call happens on
// the same thread NX started it on. No socket and no background NX API thread.
using System;
using System.Globalization;
using System.IO;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Threading;
using NXOpen;

public class VisibleBridge
{
    static System.Windows.Forms.Timer timer;
    static bool busy;
    static int thread;

    // The launcher passes the project directory explicitly: relying on MyDocuments
    // is wrong when NX starts from a scheduled task. GetFullPath normalises the
    // "..\" the launcher produces, which the path check below compares against.
    static readonly string root = Path.GetFullPath(
        Environment.GetEnvironmentVariable("ONLINE_MACHINING_ROOT")
        ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "OnlineMachiningNX"));
    static readonly string queue = Path.Combine(root, "queue-dotnet");

    public static int Startup(string[] args) { return Enter(); }
    public static int Startup() { return Enter(); }
    public static int ufsta(string[] args) { return Enter(); }
    public static int ufsta(string param) { return Enter(); }
    public static int ufsta() { return Enter(); }
    public static void Main(string[] args) { Enter(); }

    public static int GetUnloadOption(string ignored)
    {
        return (int)Session.LibraryUnloadOption.AtTermination;
    }

    static double Now()
    {
        return (DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds;
    }

    static string Q(string s)
    {
        if (s == null) s = "";
        return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"")
                       .Replace("\r", "\\r").Replace("\n", "\\n") + "\"";
    }

    static void WriteAtomic(string dest, string data)
    {
        File.WriteAllText(dest + ".tmp", data);
        if (File.Exists(dest)) File.Replace(dest + ".tmp", dest, null);
        else File.Move(dest + ".tmp", dest);
    }

    static void Status(string state, string details)
    {
        var p = Process.GetCurrentProcess();
        WriteAtomic(Path.Combine(root, "bridge-status.json"),
            "{\"state\":" + Q(state) + ",\"pid\":" + p.Id + ",\"session_id\":" + p.SessionId +
            ",\"thread_id\":" + thread + ",\"heartbeat\":" +
            Now().ToString(CultureInfo.InvariantCulture) + ",\"details\":" + Q(details) + "}");
    }

    // Errors must survive the next tick, which rewrites the status file.
    static void Log(string text)
    {
        try
        {
            File.AppendAllText(Path.Combine(root, "bridge-errors.log"),
                DateTime.Now.ToString("s") + " " + text + Environment.NewLine);
        }
        catch { }
    }

    static int Enter()
    {
        try
        {
            var p = Process.GetCurrentProcess();
            Directory.CreateDirectory(root);
            Directory.CreateDirectory(queue);
            File.AppendAllText(Path.Combine(root, "bridge-loaded.log"),
                DateTime.Now.ToString("s") + " pid=" + p.Id + " session=" + p.SessionId +
                " root=" + root + Environment.NewLine);
            if (p.SessionId == 0) throw new Exception("Visible desktop session required");
            if (timer != null) timer.Dispose();
            thread = Thread.CurrentThread.ManagedThreadId;
            // A request queued before this session started was never accepted by it.
            foreach (string f in Directory.GetFiles(queue, "*.ready"))
                File.Move(f, f + ".stale-" + DateTime.UtcNow.Ticks);
            timer = new System.Windows.Forms.Timer();
            timer.Interval = 1000;
            timer.Tick += Tick;
            timer.Start();
            Status("ready", "idle");
            return 0;
        }
        catch (Exception ex)
        {
            Log("startup: " + ex);
            try { Status("error", ex.ToString()); } catch { }
            return 1;
        }
    }

    static void Tick(object sender, EventArgs e)
    {
        if (busy) return;
        busy = true;
        string claimed = null;
        try
        {
            if (Thread.CurrentThread.ManagedThreadId != thread)
                throw new Exception("Main thread identity changed");
            string stop = Path.Combine(root, "bridge-stop");
            if (File.Exists(stop))
            {
                File.Delete(stop);
                timer.Stop();
                Status("stopped", "");
                return;
            }
            // Never nest a dispatched job inside a journal the user is playing.
            if (Session.GetSession().JournalManager.IsJournalRunning)
            {
                Status("paused", "journal running");
                return;
            }
            string[] files = Directory.GetFiles(queue, "*.ready");
            if (files.Length == 0)
            {
                Status("ready", "idle");
                return;
            }
            Array.Sort(files);
            claimed = files[0] + ".running";
            File.Move(files[0], claimed);
            Run(claimed);
            File.Move(claimed, claimed + ".done");
            claimed = null;
        }
        catch (Exception ex)
        {
            Log("tick: " + ex);
            try
            {
                if (claimed != null) File.Move(claimed, claimed + ".failed");
                Status("error", ex.ToString());
            }
            catch { }
        }
        finally { busy = false; }
    }

    static void Run(string requestFile)
    {
        string[] request = File.ReadAllLines(requestFile);
        if (request.Length < 2) throw new Exception("Request needs a job path and a SHA-256");
        string job = Path.GetFullPath(request[0].Trim());
        // Only archived job sources inside the project directory may be executed.
        if (!job.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new Exception("Job outside project directory: " + job + " (root " + root + ")");
        // Jobs are Python. Session.Execute runs a global function in a .py file in
        // this process and propagates its exceptions, unlike PlayDotNetJournal, which
        // takes only C#/VB sources and reports success even when they throw.
        if (Path.GetFileName(job) != "job.py") throw new Exception("Job must be job.py: " + job);
        string hash;
        using (var sha = SHA256.Create())
            hash = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(job))).Replace("-", "").ToLowerInvariant();
        if (hash != request[1].Trim()) throw new Exception("Source hash mismatch for " + job);

        Status("running", job);
        var p = Process.GetCurrentProcess();
        string error = "", warning = "";
        double started = Now();
        string dir = Path.GetDirectoryName(job);
        try
        {
            // The run directory goes in as an argument: NX freezes os.environ when
            // it starts its embedded interpreter, so a variable set here never
            // reaches the script.
            Session.GetSession().Execute(job, "", "main", new object[] { dir });
        }
        catch (Exception ex) { error = ex.ToString(); }

        WriteAtomic(Path.Combine(Path.GetDirectoryName(job), "bridge-execution.json"),
            "{\"execution_ok\":" + (string.IsNullOrEmpty(error) ? "true" : "false") +
            ",\"pid\":" + p.Id + ",\"session_id\":" + p.SessionId + ",\"thread_id\":" + thread +
            ",\"sha256\":" + Q(hash) + ",\"started\":" + started.ToString(CultureInfo.InvariantCulture) +
            ",\"finished\":" + Now().ToString(CultureInfo.InvariantCulture) +
            ",\"error\":" + Q(error) + ",\"warning\":" + Q(warning) + "}");
        Status("ready", job);
    }
}
