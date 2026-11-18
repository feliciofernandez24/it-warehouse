import React from "react";

export function EquipmentIcon({kind="equipment"}) {
 const paths=kind==="close"?<path d="m6 6 12 12M18 6 6 18"/>:kind==="check"?<path d="m6 12 4 4 8-8"/>:kind==="location"?<><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/></>:kind==="shield"?<><path d="M12 3 4 6v5c0 5 8 10 8 10s8-5 8-10V6Z"/><path d="m8 12 3 3 5-6"/></>:<><rect x="3" y="3" width="18" height="13" rx="2"/><path d="M8 21h8m-4-5v5M7 7h4m-4 4h8"/></>;
 return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths}</svg>;
}
export function RegistrationProgress({step}) {
 const current=step==="success"?2:step==="review"?1:0;
 return <ol className="registration-progress" aria-label="Registration progress">{["Details","Review","Complete"].map((label,i)=><li key={label} className={i<current?"complete":i===current?"current":""} aria-current={i===current?"step":undefined}><span aria-hidden="true">{i<current?"✓":i+1}</span>{label}</li>)}</ol>;
}
const labels={model_number:"Model number",part_number:"Part number",capacity_bytes:"Capacity (bytes)",memory_generation:"Memory generation",interface_type:"Interface",speed_value:"Speed",speed_unit:"Speed unit",size_value:"Size",size_unit:"Size unit",port_count:"Ports"};
const metadata=new Set(["id","pk","public_id","sku_code","name","category","category_id","category_name","manufacturer","manufacturer_id","manufacturer_name","tracking_mode","description","is_active","version","created_at","updated_at","change_reason","expected_version"]);
const title=key=>String(key).replace(/([a-z])([A-Z])/g,"$1 $2").replace(/[_-]/g," ").replace(/\b\w/g,c=>c.toUpperCase());
function scalar(value){
 if(value==null||String(value).trim()==="")return "Not provided";
 if(typeof value==="boolean")return value?"Yes":"No";
 if(typeof value==="number"&&Number.isFinite(value))return new Intl.NumberFormat("en",{maximumFractionDigits:12}).format(value);
 return String(value);
}
export function specificationEntries(product){
 const rows=[];
 function visit(value,label){
  if(Array.isArray(value)){if(!value.length)rows.push([label,"Not provided"]);else value.forEach((v,i)=>visit(v,label+" / "+(i+1)));return;}
  if(value&&typeof value==="object"){const entries=Object.entries(value);if(!entries.length)rows.push([label,"Not provided"]);else entries.forEach(([k,v])=>visit(v,label+" / "+title(k)));return;}
  rows.push([label,scalar(value)]);
 }
 Object.entries(product||{}).filter(([key])=>!metadata.has(key)).forEach(([key,value])=>{
  if(["specifications","technical_specifications","additional_specifications"].includes(key)&&value&&typeof value==="object"){
   if(Array.isArray(value))visit(value,"Specification");
   else Object.entries(value).forEach(([k,v])=>visit(v,labels[k]||title(k)));
  }else visit(value,labels[key]||title(key));
 });
 return rows;
}
export function CatalogSpecifications({product}) {
 if(!product)return null;
 const entries=specificationEntries(product),hasValues=entries.some(([,v])=>v!=="Not provided");
 return <section className="catalog-specifications" aria-label="Catalog specifications"><header><span className="registration-mini-icon"><EquipmentIcon/></span><div><h4>Catalog specifications</h4><p>Details from the selected product model</p></div><span className="catalog-readonly">Read only</span></header>
 {hasValues?<dl className="specification-grid">{entries.map(([label,value],i)=><div key={label+i}><dt>{label}</dt><dd className={value==="Not provided"?"value-empty":""}>{value}</dd></div>)}</dl>:<p className="catalog-empty">No catalog specifications have been provided for this model.</p>}
 </section>;
}
export function RegistrationSection({number,title,description,children}) {
 return <fieldset className="registration-section"><legend><span className="registration-section-number" aria-hidden="true">{number}</span>{title}</legend>{description&&<p className="registration-section-description">{description}</p>}<div className="registration-fields">{children}</div></fieldset>;
}
export function RegistrationReview({pending,product,warehouse,location,categories,manufacturers,headingRef}) {
 const category=product?.category_name||categories?.find(c=>String(c.id)===String(product?.category??product?.category_id))?.name;
 const manufacturer=product?.manufacturer_name||manufacturers?.find(m=>String(m.id)===String(product?.manufacturer??product?.manufacturer_id))?.name;
 const labelState=value=>value?value.charAt(0)+value.slice(1).toLowerCase():"Not provided";
 const rows=[
 ["Device name",pending.device_name],["Product model",product?.name],["SKU",product?.sku_code],
 ["Category",category],["Manufacturer",manufacturer],["Serial number",pending.serial_raw],
 ["Warehouse",warehouse?.name],["Storage location",location?.name],
 ["Condition",labelState(pending.condition)],["Stock state",labelState(pending.state)],
 ["Operation type","Initial stock receipt"],["Asset tag","Generated by the server after registration"],
 ["Reason / remarks",pending.reason],
 ...(pending.description?[["Description",pending.description]]:[]),
 ...(pending.external_reference?[["External reference",pending.external_reference]]:[])
 ];
 return <section className="registration-review" aria-label="Review registration">
  <div className="registration-review-heading"><span className="registration-mini-icon"><EquipmentIcon kind="shield"/></span><div><h3 ref={headingRef} tabIndex={-1}>Review asset registration</h3><p>Check the equipment and receiving details before posting.</p></div></div>
  <dl className="registration-review-grid">{rows.map(([label,value])=><div key={label} className={["Description","Reason / remarks"].includes(label)?"review-wide":""}><dt>{label}</dt><dd className={value?undefined:"value-empty"}>{value||"Not provided"}</dd></div>)}</dl>
  <div className="registration-immutable-notice"><EquipmentIcon kind="shield"/><p><strong>This will post an immutable receipt.</strong> Confirming creates one asset and its initial stock receipt. Review all details before continuing.</p></div>
 </section>;
}
export function RegistrationReceipt({result}) {
 return <div className="registration-success" role="status" tabIndex={-1}><span className="registration-success-icon"><EquipmentIcon kind="check"/></span>
  <h3>Asset registered</h3><p>The equipment and its initial stock receipt were saved successfully.</p>
  <div className="registration-success-record">{result.assets?.length?result.assets.map(a=><div key={a.id}><span>Asset tag</span><strong>{a.asset_tag}</strong></div>):<div><span>Asset reference</span><strong>{result.asset_ids?.join(", ")||"See Inventory Activity"}</strong></div>}</div>
  {result.receipt?.map(r=><div className="registration-success-receipt" key={r.id}><span>Stock receipt</span><strong>Receipt {r.public_id}</strong><small>Initial stock receipt{r.recorded_at?" · "+r.recorded_at:""}</small></div>)}
  {!result.receipt?.length&&<p>Receipt reference: {result.movement_ids?.join(", ")||"See Inventory Activity"}</p>}
  {result.warnings?.map(w=><p className="registration-result-warning" key={w}>{w}</p>)}
 </div>;
}

export function OperationReview({pending,lists}) {
 const b=pending.body;
 const asset=lists.assets?.find(x=>x.id===b.asset_id),product=lists.products?.find(x=>x.id===b.product_model_id);
 const location=id=>lists.locations?.find(x=>x.id===id)?.name||(id?"Location "+id:"Not applicable");
 const recipient=lists.recipients?.find(x=>x.id===b.recipient_id)?.name;
 const rows=[["Operation",({receive:"Bulk stock receipt",transfer:"Stock transfer",issue:"Equipment issue",return:"Equipment return"})[pending.action]||"Stock transaction"],
 ["Equipment / product",asset?.asset_tag||product?.name||(b.asset_id?"Asset "+b.asset_id:"Not provided")],["Quantity",b.quantity??1],
 ["Source",location(b.source_location_id)],["Destination",location(b.destination_location_id)],
 ...(recipient?[["Recipient",recipient]]:[]),...(b.condition?[["Condition",b.condition]]:[]),
 ...(b.state?[["Stock state",b.state]]:[]),["Reason / remarks",b.reason],...(b.external_reference?[["External reference",b.external_reference]]:[])];
 return <div className="registration-review"><h3>Review transaction</h3><dl className="registration-review-grid">{rows.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><div className="registration-immutable-notice"><EquipmentIcon kind="shield"/><p>Confirming posts an immutable inventory transaction. Check the item, locations and quantity before continuing.</p></div></div>;
}
export function OperationReceipt({result}) {
 return <div role="status" className="registration-success"><span className="registration-success-icon"><EquipmentIcon kind="check"/></span><h3>Transaction recorded</h3>
 {result.assets?.map(a=><p key={a.id}>{a.asset_tag}</p>)}
 {result.receipt?.map(r=><p key={r.id}>Receipt {r.public_id}</p>)}
 {!result.receipt?.length&&<p>Movement reference: {result.movement_ids?.join(", ")}</p>}
 {result.warnings?.map(w=><p key={w}>{w}</p>)}</div>;
}
