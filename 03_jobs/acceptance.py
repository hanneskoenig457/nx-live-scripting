"""NX capability test: parametric cylinder, associative drawing, tolerance and PDF.
Setup specimen only, not a manufacturing release.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.Drawings
import NXOpen.Annotations
import NXOpen.Preferences
import NXOpen.UF

OUT=Path(__file__).resolve().parent
result={'ok':False,'stage':'start'}

def checkpoint(stage):
    result['stage']=stage
    (OUT/'result.json').write_text(json.dumps(result,indent=2))

def trace(label,view):
    result.setdefault('view_trace',[]).append(
        {'at':label,'out_of_date':view.IsOutOfDate,'visible_objects':len(view.AskVisibleObjects())})
    checkpoint(result['stage'])

def main():
    s=NXOpen.Session.GetSession()
    part=s.Parts.NewDisplay(str(OUT/'acceptance.prt'),NXOpen.Part.Units.Millimeters)
    checkpoint('create cylinder')
    b=part.Features.CreateCylinderBuilder(None)
    b.Type=NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
    b.Origin=NXOpen.Point3d(0.0,0.0,0.0)
    b.Direction=NXOpen.Vector3d(1.0,0.0,0.0)
    b.Diameter.RightHandSide='20'
    b.Height.RightHandSide='60'
    feature=b.CommitFeature()
    b.Destroy()
    body=feature.GetBodies()[0]
    result['body_count']=len(list(part.Bodies))
    checkpoint('create sheet')
    sb=part.DrawingSheets.DrawingSheetBuilder(None)
    sb.Option=NXOpen.Drawings.DrawingSheetBuilder.SheetOption.CustomSize
    sb.Units=NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
    sb.Length=297.0
    sb.Height=210.0
    sb.Name='NX_AUTOMATION_TEST'
    sb.ScaleNumerator=1.0
    sb.ScaleDenominator=1.0
    sb.ProjectionAngle=NXOpen.Drawings.DrawingSheetBuilder.SheetProjectionAngle.First
    sheet=sb.Commit()
    sb.Destroy()
    sheet.Open()
    checkpoint('create base view')
    view=sheet.SheetDraftingViews.CreateBaseView(part.ModelingViews.FindObject('Top'),NXOpen.Point3d(110.0,110.0,0.0),1.0,False)
    # Generate the view geometry before anything attaches to it. Updating only after
    # the dimensions exist leaves the view out of date in batch, which silently
    # exports a drawing without part contours.
    trace('after create',view)
    view.Update()
    trace('after first update',view)
    checkpoint('create associative dimension')
    edges=sorted(body.GetEdges(),key=lambda e:e.GetVertices()[0].X)
    data=part.Annotations.NewDimensionData()
    for index,edge in enumerate([edges[0],edges[-1]],1):
        assoc=part.Annotations.NewAssociativity()
        assoc.FirstObject=edge
        assoc.ObjectView=view
        assoc.PointOption=NXOpen.Annotations.AssociativityPointOption.ArcCenter
        data.SetAssociativity(index,[assoc])
    dim=part.Dimensions.CreateHorizontalDimension(data,NXOpen.Point3d(110.0,85.0,0.0))
    dim.ToleranceType=NXOpen.Annotations.ToleranceType.BilateralTwoLines
    dim.UpperMetricToleranceValue=0.02
    dim.LowerMetricToleranceValue=-0.01
    dim.ToleranceDecimalPlaces=2
    result['dimension']={'size':dim.ComputedSize,'upper':dim.UpperMetricToleranceValue,'lower':dim.LowerMetricToleranceValue}
    trace('after dimension',view)
    checkpoint('update views')
    view.Update()
    trace('after second update',view)
    part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All,sheet)
    trace('after UpdateViews',view)
    # A view that is still out of date exports as an empty frame. Fail loudly here
    # rather than shipping a drawing whose geometry is missing.
    result['view']={'out_of_date':view.IsOutOfDate,'visible_objects':len(view.AskVisibleObjects())}
    assert result['view']['out_of_date'] is False, result['view']
    assert result['view']['visible_objects']>0, result['view']
    checkpoint('export PDF')
    pdf=part.PlotManager.CreatePrintPdfbuilder()
    pdf.Filename=str(OUT/'acceptance.pdf')
    pdf.SourceBuilder.SetSheets([sheet])
    pdf.Colors=NXOpen.PrintPDFBuilder.Color.BlackOnWhite
    pdf.Size=NXOpen.PrintPDFBuilder.SizeOption.FullScale
    pdf.OutputText=NXOpen.PrintPDFBuilder.OutputTextOption.Text
    pdf.Commit()
    pdf.Destroy()
    checkpoint('save part')
    status=part.Save(NXOpen.BasePart.SaveComponents.TrueValue,NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    assert abs(dim.ComputedSize-60)<1e-6, result['dimension']
    assert (OUT/'acceptance.pdf').stat().st_size>100
    result['ok']=True
    checkpoint('complete')

if __name__=='__main__':
    try:
        main()
    except Exception:
        result['error']=traceback.format_exc()
        (OUT/'result.json').write_text(json.dumps(result,indent=2))
