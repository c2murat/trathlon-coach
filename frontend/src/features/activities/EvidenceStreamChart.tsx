import {useId,useMemo,useState} from "react";
import type {ActivityEvidence,EvidenceStream} from "../../types/api";
import {extent,formatSeriesValue,formatX,prepareSeries,scale,selectXAxis,stableTicks} from "./evidenceChartUtils";

const WIDTH=720,HEIGHT=320,LEFT=92,RIGHT=24,TOP=24,BOTTOM=64;
export function EvidenceStreamChart({evidence,streamKey,stream}:{evidence:ActivityEvidence;streamKey:string;stream:EvidenceStream}){
 const titleId=useId(),descriptionId=useId(),[active,setActive]=useState<number|null>(null),[showPoints,setShowPoints]=useState(stream.sample_count<=12);
 const model=useMemo(()=>{const series=prepareSeries(streamKey,stream),xAxis=selectXAxis(evidence,series.values.length),valid=series.values.flatMap(value=>value===null?[]:[value]),yExtent=extent(valid),xExtent=extent(xAxis.values)??{min:0,max:1},yTicks=yExtent?stableTicks(yExtent.min,yExtent.max):[],xTicks=stableTicks(xExtent.min,xExtent.max,5),points=series.values.flatMap((value,index)=>value===null||xAxis.values[index]===undefined?[]:[{index,value,xValue:xAxis.values[index],x:scale(xAxis.values[index],xExtent.min,xExtent.max,LEFT,WIDTH-RIGHT),y:scale(value,yExtent!.min,yExtent!.max,HEIGHT-BOTTOM,TOP)}]);return {series,xAxis,yExtent,xExtent,yTicks,xTicks,points}},[evidence,stream,streamKey]);
 if(!model.yExtent||!model.points.length)return <p className="evidence-empty">Este stream no contiene valores representables.</p>;
 const current=active===null?null:model.points.find(point=>point.index===active)??null;
 const path=model.points.map((point,index)=>`${index?"L":"M"} ${point.x} ${point.y}`).join(" ");
 return <div className="stream-chart-wrap"><div className="chart-display-controls"><label><input type="checkbox" checked={showPoints} onChange={event=>setShowPoints(event.target.checked)}/> Mostrar puntos</label></div>
  <div className="stream-chart-stage">
   <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby={`${titleId} ${descriptionId}`}>
    <title id={titleId}>{model.series.label} por {model.xAxis.label.toLowerCase()}</title>
    <desc id={descriptionId}>Serie factual con {model.points.length} valores representables. Los puntos se pueden recorrer con el teclado.</desc>
    <g className="chart-grid" aria-hidden="true">{model.yTicks.map((tick,index)=><line key={`y-${index}`} x1={LEFT} x2={WIDTH-RIGHT} y1={scale(tick,model.yExtent!.min,model.yExtent!.max,HEIGHT-BOTTOM,TOP)} y2={scale(tick,model.yExtent!.min,model.yExtent!.max,HEIGHT-BOTTOM,TOP)}/>)}{model.xTicks.map((tick,index)=><line key={`x-${index}`} y1={TOP} y2={HEIGHT-BOTTOM} x1={scale(tick,model.xExtent.min,model.xExtent.max,LEFT,WIDTH-RIGHT)} x2={scale(tick,model.xExtent.min,model.xExtent.max,LEFT,WIDTH-RIGHT)}/>)}</g>
    <g className="chart-axes" aria-hidden="true"><line x1={LEFT} x2={WIDTH-RIGHT} y1={HEIGHT-BOTTOM} y2={HEIGHT-BOTTOM}/><line x1={LEFT} x2={LEFT} y1={TOP} y2={HEIGHT-BOTTOM}/></g>
    <g className="chart-ticks" aria-hidden="true">{model.yTicks.map((tick,index)=><text key={`yl-${index}`} x={LEFT-10} y={scale(tick,model.yExtent!.min,model.yExtent!.max,HEIGHT-BOTTOM,TOP)+4} textAnchor="end">{formatSeriesValue(streamKey,tick)}</text>)}{model.xTicks.map((tick,index)=><text key={`xl-${index}`} x={scale(tick,model.xExtent.min,model.xExtent.max,LEFT,WIDTH-RIGHT)} y={HEIGHT-BOTTOM+22} textAnchor={index===0?"start":index===model.xTicks.length-1?"end":"middle"}>{formatX(model.xAxis.kind,tick)}</text>)}</g>
    <text className="chart-axis-label" x={(LEFT+WIDTH-RIGHT)/2} y={HEIGHT-12} textAnchor="middle">{model.xAxis.label}</text><text className="chart-axis-label" transform={`translate(24 ${(TOP+HEIGHT-BOTTOM)/2}) rotate(-90)`} textAnchor="middle">{model.series.label} ({model.series.unit})</text>
    {model.points.length>1&&<path className="chart-data-line" d={path} vectorEffect="non-scaling-stroke"/>}
    <g className={showPoints?"chart-data-points chart-data-points--visible":"chart-data-points"}>{model.points.map(point=><circle key={point.index} cx={point.x} cy={point.y} r={active===point.index?7:5} tabIndex={0} role="button" aria-label={`${model.series.label}: ${formatSeriesValue(streamKey,point.value)} ${model.series.unit}; ${model.xAxis.label}: ${formatX(model.xAxis.kind,point.xValue)}; muestra ${point.index+1}`} onMouseEnter={()=>setActive(point.index)} onMouseLeave={()=>setActive(null)} onFocus={()=>setActive(point.index)} onBlur={()=>setActive(null)}/>)}</g>{current&&<circle className="chart-active-point" cx={current.x} cy={current.y} r={7} aria-hidden="true"/>}
   </svg>
   {current&&<div role="tooltip" className="chart-tooltip" style={{left:`${Math.min(82,Math.max(18,current.x/WIDTH*100))}%`,top:`${Math.min(78,Math.max(12,current.y/HEIGHT*100))}%`}}><span>{model.xAxis.label}: {formatX(model.xAxis.kind,current.xValue)}</span><strong>{model.series.label}</strong><span className="chart-tooltip__value">{formatSeriesValue(streamKey,current.value)} {model.series.unit}</span><small>Muestra {current.index+1}</small></div>}
  </div>
  {model.xAxis.warning&&<p className="chart-warning" role="status">{model.xAxis.warning}</p>}
  <p className="chart-axis">Eje X: {model.xAxis.label}. Eje Y: {model.series.label} ({model.series.unit}).</p>
  <details><summary>Alternativa textual del gráfico</summary><ol>{model.points.slice(0,20).map(point=><li key={point.index}>Muestra {point.index+1}: {model.series.label} {formatSeriesValue(streamKey,point.value)} {model.series.unit}; {model.xAxis.label.toLowerCase()} {formatX(model.xAxis.kind,point.xValue)}.</li>)}</ol></details>
 </div>
}
