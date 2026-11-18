import React,{forwardRef,useEffect,useLayoutEffect,useId,useImperativeHandle,useRef,useState} from "react";
import {api,request,errorMessages} from "./api";
import {CatalogSpecifications,RegistrationSection,RegistrationReview,RegistrationReceipt,RegistrationProgress,EquipmentIcon} from "./RegistrationPresentation";
export {RegistrationReceipt} from "./RegistrationPresentation";

const fieldLabels={device_name:"Device name",serial_raw:"Serial number",product_model_id:"Product model",destination_location_id:"Storage location",condition:"Condition",state:"Stock state",reason:"Reason / remarks",description:"Description",external_reference:"External reference"};
function registrationErrors(value){return errorMessages(value).map(message=>message.replace(/^([a-z_]+):/,(_,key)=>(fieldLabels[key]||key.replaceAll("_"," "))+":"));}

const requiredPermissions=["transactions.receive_stock","inventory.add_asset","inventory.view_asset","inventory.view_productmodel","warehouse.view_warehouse","warehouse.view_storagelocation"];
export const canRegisterAsset=user=>user.manual_inventory_enabled===true&&requiredPermissions.every(p=>user.permissions.includes(p));

export const SerializedAssetRegistration=forwardRef(function SerializedAssetRegistration(
 {user,onSuccess,onStateChange,autoFocus=false,allowAnother=true,embedded=false,externalActions=false},ref
){
 const [data,setData]=useState({}),[lists,setLists]=useState({}),[loading,setLoading]=useState(true);
 const [lookupRevision,setLookupRevision]=useState(0),[lookupError,setLookupError]=useState("");
 const [pending,setPending]=useState(null),[busy,setBusy]=useState(false),[result,setResult]=useState(null),[error,setError]=useState(""),[errors,setErrors]=useState(null);
 const [category,setCategory]=useState(""),[manufacturer,setManufacturer]=useState("");
 const inFlight=useRef(false),completed=useRef(false),pendingRef=useRef(null),uncertain=useRef(false),first=useRef(null),success=useRef(null),reviewHeading=useRef(null),formElement=useRef(null);
 const id=useId(),permitted=canRegisterAsset(user),step=result?"success":pending?"review":"details";
 const dirty=!result&&(Boolean(category||manufacturer||pending)||Object.values(data).some(v=>String(v??"").length>0));
 useImperativeHandle(ref,()=>({
  getCloseState:()=>({busy:inFlight.current,dirty,uncertain:uncertain.current}),
  review:()=>formElement.current?.requestSubmit(),confirm:()=>post(),back:()=>editPending()
 }));
 useLayoutEffect(()=>{onStateChange?.({busy,pending:Boolean(pending),dirty,step,loading,canSubmit:permitted&&!loading&&!lookupError});},[busy,pending,dirty,step,loading,permitted,lookupError,onStateChange]);
 useEffect(()=>{
  if(!permitted){setLoading(false);return;}
  const controller=new AbortController();let active=true;setLoading(true);setLookupError("");
  const endpoints={products:["management/product-models","inventory.view_productmodel"],warehouses:["warehouses","warehouse.view_warehouse"],locations:["locations","warehouse.view_storagelocation"],categories:["inventory/categories","inventory.view_assetcategory"],manufacturers:["inventory/manufacturers","inventory.view_manufacturer"]};
  async function load(){
   const entries=await Promise.all(Object.entries(endpoints).map(async([key,[path,permission]])=>{
    if(!user.permissions.includes(permission))return [key,[]];
    let next="/api/"+path+"/?page_size=100",rows=[];
    while(next){const page=await request(next,{signal:controller.signal});rows=rows.concat(page.results);next=page.next?new URL(page.next,window.location.origin).pathname+new URL(page.next,window.location.origin).search:null;}
    return [key,rows];
   }));
   if(active)setLists(Object.fromEntries(entries));
  }
  load().catch(e=>{if(active&&e.name!=="AbortError")setLookupError(e.message);}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[user,permitted,lookupRevision]);
 useEffect(()=>{if(autoFocus&&!loading&&!lookupError&&permitted&&step==="details")first.current?.focus();},[autoFocus,loading,lookupError,permitted,step]);
 useEffect(()=>{if(step==="success")success.current?.querySelector('[role="status"]')?.focus();if(step==="review")reviewHeading.current?.focus();},[step]);
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
   else{uncertain.current=true;setError(e.message+" Retry this registration without changing its details.");}
   return;
  }finally{inFlight.current=false;setBusy(false);}
  completed.current=true;pendingRef.current=null;uncertain.current=false;setPending(null);setData({});setResult(response);onSuccess?.(response);
 }
 function editPending(){
  if(inFlight.current)return;
  if(uncertain.current&&!window.confirm("The registration result is unconfirmed. Check Inventory Activity before editing or starting again. Return to editing?"))return;
  pendingRef.current=null;uncertain.current=false;setPending(null);setError("");setErrors(null);
 }
 function another(){completed.current=false;pendingRef.current=null;uncertain.current=false;setResult(null);setData({});setError("");setErrors(null);}
 const products=(lists.products||[]).filter(p=>p.is_active&&p.tracking_mode==="SERIALIZED"&&(!category||String(p.category??p.category_id)===category)&&(!manufacturer||String(p.manufacturer??p.manufacturer_id)===manufacturer));
 const product=(lists.products||[]).find(p=>String(p.id)===String(data.product_model_id));
 const warehouses=(lists.warehouses||[]).filter(w=>w.is_active);
 const locations=(lists.locations||[]).filter(l=>l.is_active&&String(l.warehouse_id)===String(data.warehouse_id));
 const selectedWarehouse=(lists.warehouses||[]).find(w=>String(w.id)===String(pending?.warehouse_id||data.warehouse_id));
 const selectedLocation=(lists.locations||[]).find(l=>String(l.id)===String(pending?.destination_location_id||data.destination_location_id));
 function fieldError(key){return errors?.[key]?<small className="error" id={id+"-"+key+"-error"} role="alert">{errorMessages(errors[key]).join(" ")}</small>:null;}
 function select(label,key,items,caption,reference){
  return <div className="editor-field is-required"><label htmlFor={id+"-"+key}>{label}</label><select ref={reference} id={id+"-"+key} required value={data[key]||""} aria-invalid={Boolean(errors?.[key])} aria-describedby={errors?.[key]?id+"-"+key+"-error":undefined} onChange={e=>update(key,e.target.value)}><option value="">Select {label.toLowerCase()}</option>{items.map(item=><option key={item.id} value={item.id}>{caption(item)}</option>)}</select>{fieldError(key)}</div>;
 }
 function text(label,key,{required=true,max=500,textarea=false}={}){
  const props={id:id+"-"+key,value:data[key]||"",required,maxLength:max,"aria-invalid":Boolean(errors?.[key]),"aria-describedby":errors?.[key]?id+"-"+key+"-error":undefined,onChange:e=>update(key,e.target.value)};
  return <div className={"editor-field"+(required?" is-required":"")}><label htmlFor={props.id}>{label}</label>{textarea?<textarea {...props} rows={2}/>:<input {...props}/>} {fieldError(key)}</div>;
 }
 return <section className={"serialized-registration"+(embedded?" embedded-registration":"")}>
  {!embedded&&<header className="registration-inline-heading"><span className="registration-header-icon"><EquipmentIcon/></span><div><h2>Register New Asset</h2><p>Add equipment with a traceable initial stock receipt.</p></div></header>}
  {!embedded&&<RegistrationProgress step={step}/>}
  {!permitted?<p role="alert" className="registration-error-banner">Manual asset registration is disabled or you do not have the required permissions.</p>:<>
   {error&&<p className="registration-error-banner" role="alert">{error}</p>}
   {errors&&<div className="registration-field-summary" role="alert">{registrationErrors(errors).filter(Boolean).map((message,i)=><p key={i}>{message}</p>)}</div>}
   {result?<div ref={success}><RegistrationReceipt result={result}/>{allowAnother&&<button className="primary" type="button" onClick={another}>Register another asset</button>}</div>:loading?<div role="status" className="registration-loading"><span className="spinner"/><p>Loading registration choices…</p></div>:lookupError?<div className="registration-error-banner" role="alert"><p>{lookupError}</p><button type="button" onClick={()=>setLookupRevision(x=>x+1)}>Retry loading choices</button></div>:pending?
    <RegistrationReview pending={pending} product={product} warehouse={selectedWarehouse} location={selectedLocation} categories={lists.categories} manufacturers={lists.manufacturers} headingRef={reviewHeading}/>:
    <form ref={formElement} id={id+"-form"} className="registration-form" onSubmit={prepare}>
     <RegistrationSection number="01" title="Product information" description="Choose an existing serialized product model.">
      <div className="editor-field"><label htmlFor={id+"-category"}>Category filter</label><select id={id+"-category"} value={category} onChange={e=>{setCategory(e.target.value);update("product_model_id","");}}><option value="">All categories</option>{(lists.categories||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div className="editor-field"><label htmlFor={id+"-manufacturer"}>Manufacturer filter</label><select id={id+"-manufacturer"} value={manufacturer} onChange={e=>{setManufacturer(e.target.value);update("product_model_id","");}}><option value="">All manufacturers</option>{(lists.manufacturers||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div className="registration-wide">{select("Product model","product_model_id",products,p=>p.sku_code+" — "+p.name,first)}</div>
      <CatalogSpecifications product={product}/>
     </RegistrationSection>
     <RegistrationSection number="02" title="Equipment details" description="Record the name and serial shown on the equipment.">
      {text("Device name","device_name",{max:200})}{text("Serial number (optional)","serial_raw",{required:false,max:200})}
     </RegistrationSection>
     <RegistrationSection number="03" title="Warehouse and location">
      {select("Destination warehouse","warehouse_id",warehouses,w=>w.name)}
      {select("Destination location","destination_location_id",locations,l=>l.name+" ("+l.code+")")}
     </RegistrationSection>
     <RegistrationSection number="04" title="Condition and stock state">
      {select("Condition","condition",["NEW","USED","REFURBISHED","BROKEN","UNKNOWN"].map(id=>({id})),p=>p.id.charAt(0)+p.id.slice(1).toLowerCase())}
      {select("Stock state","state",["AVAILABLE","QUARANTINED"].map(id=>({id})),p=>p.id.charAt(0)+p.id.slice(1).toLowerCase())}
     </RegistrationSection>
     <RegistrationSection number="05" title="Description and remarks">
      {text("Description (optional)","description",{required:false,max:4000,textarea:true})}
      {text("Reason / remarks","reason",{textarea:true})}
      <div className="registration-wide">{text("External reference (optional)","external_reference",{required:false,max:160})}</div>
     </RegistrationSection>
    </form>
   }
   {!externalActions&&!result&&!loading&&!lookupError&&<footer className="registration-inline-actions"><span>Required fields are marked <b aria-hidden="true">*</b></span><div>{pending?<><button type="button" disabled={busy} onClick={editPending}>Back to edit</button><button className="primary" type="button" disabled={busy} onClick={post}>{busy?"Registering…":"Confirm & register"}</button></>:<button className="primary" type="submit" form={id+"-form"}>Review registration</button>}</div></footer>}
  </>}
 </section>;
});
