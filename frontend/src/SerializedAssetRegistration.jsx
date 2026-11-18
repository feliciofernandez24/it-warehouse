import React, {forwardRef,useEffect,useLayoutEffect,useId,useImperativeHandle,useRef,useState} from "react";
import {api,request,errorMessages} from "./api";

const requiredPermissions=["transactions.receive_stock","inventory.add_asset","inventory.view_asset","inventory.view_productmodel","warehouse.view_warehouse","warehouse.view_storagelocation"];
export const canRegisterAsset=user=>user.manual_inventory_enabled===true&&requiredPermissions.every(p=>user.permissions.includes(p));

export function RegistrationReceipt({result}) {
 return <div className="success-notice registration-success" role="status" tabIndex={-1}>
  <strong>Posted operation {result.operation_key}.</strong>
  <p>Assets: {result.assets?.map(a=>a.asset_tag).join(", ")||result.asset_ids?.join(", ")}</p>
  <p>Movements: {result.movement_ids?.join(", ")}</p>
  {result.receipt?.map(r=><p key={r.id}>Receipt {r.public_id} · {r.operation_type} · {r.recorded_at}</p>)}
  {result.warnings?.map(w=><p key={w}>{w}</p>)}
 </div>;
}

// One serialized-registration request builder and posting boundary for both hosts.
export const SerializedAssetRegistration=forwardRef(function SerializedAssetRegistration(
 {user,onSuccess,onStateChange,autoFocus=false,allowAnother=true},ref
) {
 const [data,setData]=useState({}),[lists,setLists]=useState({}),[loading,setLoading]=useState(true);
 const [lookupRevision,setLookupRevision]=useState(0),[lookupError,setLookupError]=useState("");
 const [pending,setPending]=useState(null),[busy,setBusy]=useState(false),[result,setResult]=useState(null),[error,setError]=useState(""),[errors,setErrors]=useState(null);
 const [category,setCategory]=useState(""),[manufacturer,setManufacturer]=useState("");
 const inFlight=useRef(false),completed=useRef(false),pendingRef=useRef(null),uncertain=useRef(false),first=useRef(null),success=useRef(null);
 const id=useId(),permitted=canRegisterAsset(user);
 const dirty=!result&&(Boolean(category||manufacturer||pending)||Object.values(data).some(v=>String(v??"").length>0));
 useImperativeHandle(ref,()=>({getCloseState:()=>({busy:inFlight.current,dirty,uncertain:uncertain.current,operationKey:pendingRef.current?.operation_key})}),[dirty]);
 useLayoutEffect(()=>{onStateChange?.({busy,pending:Boolean(pending),dirty});},[busy,pending,dirty,onStateChange]);
 useEffect(()=>{
  if(!permitted){setLoading(false);return;}
  const controller=new AbortController();let active=true;setLoading(true);setLookupError("");
  const endpoints={products:["management/product-models","inventory.view_productmodel"],warehouses:["warehouses","warehouse.view_warehouse"],locations:["locations","warehouse.view_storagelocation"],categories:["inventory/categories","inventory.view_assetcategory"],manufacturers:["inventory/manufacturers","inventory.view_manufacturer"]};
  async function load(){
   const entries=await Promise.all(Object.entries(endpoints).map(async([key,[path,permission]])=>{
    if(!user.permissions.includes(permission))return [key,[]];
    let next="/api/"+path+"/?page_size=100",rows=[];
    while(next){
     const page=await request(next,{signal:controller.signal});rows=rows.concat(page.results);
     next=page.next?new URL(page.next,window.location.origin).pathname+new URL(page.next,window.location.origin).search:null;
    }
    return [key,rows];
   }));
   if(active)setLists(Object.fromEntries(entries));
  }
  load().catch(e=>{if(active&&e.name!=="AbortError")setLookupError(e.message);}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[user,permitted,lookupRevision]);
 useEffect(()=>{if(autoFocus&&!loading&&!lookupError&&permitted)first.current?.focus();},[autoFocus,loading,lookupError,permitted]);
 useEffect(()=>{if(result)success.current?.querySelector('[role="status"]')?.focus();},[result]);
 function update(key,value){
  if(pendingRef.current||inFlight.current)return;
  setData(old=>({...old,[key]:value,...(key==="warehouse_id"?{destination_location_id:""}:{})}));
  setErrors(old=>{if(!old)return null;const next={...old};delete next[key];return Object.keys(next).length?next:null;});
 }
 function prepare(event){
  event.preventDefault();
  if(!permitted||loading||lookupError||pendingRef.current||inFlight.current||completed.current)return;
  const body={operation_key:crypto.randomUUID(),product_model_id:Number(data.product_model_id),destination_location_id:Number(data.destination_location_id),
   device_name:data.device_name,serial_raw:data.serial_raw||"",description:data.description||"",condition:data.condition,state:data.state,reason:data.reason,external_reference:data.external_reference||""};
  pendingRef.current=body;uncertain.current=false;setPending(body);setError("");setErrors(null);
 }
 async function post(){
  if(!pendingRef.current||inFlight.current||completed.current)return;
  inFlight.current=true;setBusy(true);setError("");setErrors(null);
  let response;
  try{response=await api.save("/api/transactions/manual/register/","POST",pendingRef.current);}
  catch(e){
   setError(e.message);setErrors(e.details||null);
   if(e.status===400){pendingRef.current=null;setPending(null);uncertain.current=false;}
   else{uncertain.current=true;setError(e.message+" Retry uses the same operation key and unchanged values.");}
   return;
  }finally{inFlight.current=false;setBusy(false);}
  completed.current=true;pendingRef.current=null;uncertain.current=false;
  setPending(null);setData({});setResult(response);
  onSuccess?.(response);
 }
 function editPending(){
  if(inFlight.current)return;
  if(uncertain.current&&!window.confirm("The posting result is unconfirmed. Verify activity before abandoning this operation key. Edit the request?"))return;
  pendingRef.current=null;uncertain.current=false;setPending(null);
 }
 function another(){
  completed.current=false;pendingRef.current=null;uncertain.current=false;setResult(null);setData({});setError("");setErrors(null);
 }
 const locked=Boolean(pending)||busy;
 const products=(lists.products||[]).filter(p=>p.is_active&&p.tracking_mode==="SERIALIZED"&&(!category||String(p.category??p.category_id)===category)&&(!manufacturer||String(p.manufacturer??p.manufacturer_id)===manufacturer));
 const product=products.find(p=>String(p.id)===String(data.product_model_id));
 const warehouses=(lists.warehouses||[]).filter(w=>w.is_active);
 const locations=(lists.locations||[]).filter(l=>l.is_active&&String(l.warehouse_id)===String(data.warehouse_id));
 function fieldError(key){return errors?.[key]?<small className="error" id={id+"-"+key+"-error"} role="alert">{errorMessages(errors[key]).join(" ")}</small>:null;}
 function select(label,key,items,caption,reference){
  return <div className="editor-field"><label htmlFor={id+"-"+key}>{label}</label>
   <select ref={reference} id={id+"-"+key} required value={data[key]||""} disabled={locked} aria-invalid={Boolean(errors?.[key])} aria-describedby={errors?.[key]?id+"-"+key+"-error":undefined} onChange={e=>update(key,e.target.value)}>
    <option value="">Choose {label.toLowerCase()}</option>{items.map(item=><option key={item.id} value={item.id}>{caption(item)}</option>)}
   </select>{fieldError(key)}</div>;
 }
 function text(label,key,{required=true,max=500,textarea=false}={}){
  const props={id:id+"-"+key,value:data[key]||"",required,maxLength:max,disabled:locked,"aria-invalid":Boolean(errors?.[key]),"aria-describedby":errors?.[key]?id+"-"+key+"-error":undefined,onChange:e=>update(key,e.target.value)};
  return <div className="editor-field"><label htmlFor={props.id}>{label}</label>{textarea?<textarea {...props} rows={3}/>:<input {...props}/>} {fieldError(key)}</div>;
 }
 return <section className="serialized-registration">
  <h2>Register New Asset</h2>
  {!permitted?<p role="alert">Manual asset registration is disabled or you do not have the required permissions.</p>:<>
   {error&&<p className="notice error" role="alert">{error}</p>}
   {errors&&<div className="notice error" role="alert">{errorMessages(errors).filter(Boolean).map((message,i)=><p key={i}>{message}</p>)}</div>}
   {result?<div ref={success}><RegistrationReceipt result={result}/>{allowAnother&&<button type="button" onClick={another}>Register another asset</button>}</div>:loading?<p role="status">Loading registration choices…</p>:lookupError?<div role="alert"><p>{lookupError}</p><button type="button" onClick={()=>setLookupRevision(x=>x+1)}>Retry loading choices</button></div>:<>
    <form className="registration-form" onSubmit={prepare}>
     <div className="registration-fields">
      <div className="editor-field"><label htmlFor={id+"-category"}>Category filter</label><select id={id+"-category"} value={category} disabled={locked} onChange={e=>{setCategory(e.target.value);update("product_model_id","");}}><option value="">All categories</option>{(lists.categories||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div className="editor-field"><label htmlFor={id+"-manufacturer"}>Manufacturer filter</label><select id={id+"-manufacturer"} value={manufacturer} disabled={locked} onChange={e=>{setManufacturer(e.target.value);update("product_model_id","");}}><option value="">All manufacturers</option>{(lists.manufacturers||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      {select("Product model","product_model_id",products,p=>p.sku_code+" — "+p.name,first)}
      {product&&<p className="registration-wide">Catalog specifications: {JSON.stringify(Object.fromEntries(Object.entries(product).filter(([k,v])=>["model_number","part_number","capacity_bytes","memory_generation","interface_type","speed_value","speed_unit","size_value","size_unit","port_count"].includes(k)&&v)))}</p>}
      {text("Device name","device_name",{max:200})}
      {text("Serial number (optional)","serial_raw",{required:false,max:200})}
      {text("Description (optional)","description",{required:false,max:4000,textarea:true})}
      {select("Destination warehouse","warehouse_id",warehouses,w=>w.name)}
      {select("Destination location","destination_location_id",locations,l=>l.name+" ("+l.code+")")}
      {select("Condition","condition",["NEW","USED","REFURBISHED","BROKEN","UNKNOWN"].map(id=>({id})),p=>p.id)}
      {select("Stock state","state",["AVAILABLE","QUARANTINED"].map(id=>({id})),p=>p.id)}
      {text("Reason / remarks","reason",{textarea:true})}
      {text("External reference (optional)","external_reference",{required:false,max:160})}
     </div>
     <p>Asset tag and registration time are generated by the server when the receipt is posted. Choose an existing product model; create missing catalog records before registration.</p>
     {!pending&&<button className="primary" type="submit">Review transaction</button>}
    </form>
    {pending&&<section className="registration-confirmation" role="group" aria-label="Confirm stock transaction">
     <h3>Confirm stock transaction</h3><pre>{JSON.stringify(pending,null,2)}</pre>
     <button className="primary" type="button" disabled={busy} onClick={post}>{busy?"Posting…":"Confirm and post"}</button>
     <button type="button" disabled={busy} onClick={editPending}>Edit request</button>
    </section>}
   </>}
  </>}
 </section>;
});
