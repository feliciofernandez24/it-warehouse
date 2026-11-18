import React, {useEffect,useState} from "react";
import {api,request,errorMessages} from "./api";
import {SerializedAssetRegistration} from "./SerializedAssetRegistration";

const capabilities={register:"receive_stock",receive:"receive_stock",transfer:"transfer_stock",issue:"issue_stock",return:"return_stock"};
export function InventoryOperations({user}) {
 const [registrationState,setRegistrationState]=useState({busy:false,pending:false}),[action,setAction]=useState("register"),[data,setData]=useState({}),[lists,setLists]=useState({}),[errors,setErrors]=useState(null),[error,setError]=useState(""),[result,setResult]=useState(null),[pending,setPending]=useState(null),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0),[category,setCategory]=useState(""),[manufacturer,setManufacturer]=useState("");
 const permitted=(a)=>user.permissions.includes("transactions."+capabilities[a]);
 useEffect(()=>{let active=true;setError("");
 const endpoints={products:["management/product-models","inventory.view_productmodel"],assets:["inventory/assets","inventory.view_asset"],locations:["locations","warehouse.view_storagelocation"],warehouses:["warehouses","warehouse.view_warehouse"],categories:["inventory/categories","inventory.view_assetcategory"],manufacturers:["inventory/manufacturers","inventory.view_manufacturer"],recipients:["transactions/recipients","accounts.view_assetrecipient"],assignments:["transactions/assignments","transactions.view_assetassignment"],balances:["transactions/balances","inventory.view_stockbalance"],movements:["transactions/movements","transactions.view_stockmovement"]};
 async function load(){
  const values={};
  for(const [name,[path,permission]] of Object.entries(endpoints)){
   if(action==="register"&&name!=="movements"){values[name]=[];continue;}
   if(!user.permissions.includes(permission)){values[name]=[];continue;}
   let url="/api/"+path+"/?page_size=100",rows=[];
   while(url){const page=await request(url);rows=rows.concat(page.results);url=page.next?new URL(page.next,window.location.origin).pathname+new URL(page.next,window.location.origin).search:null;}
   values[name]=rows;
  }
  if(active)setLists(values);
 }
 load().catch(e=>active&&setError(e.message));return()=>{active=false};
 },[user,revision,action]);
 const set=(key,value)=>setData(d=>({...d,[key]:value}));
 const product=(lists.products||[]).find(p=>String(p.id)===String(data.product_model_id));
 const asset=(lists.assets||[]).find(p=>String(p.id)===String(data.asset_id));
 const assignment=(lists.assignments||[]).find(p=>String(p.id)===String(data.assignment_id));
 const balance=(lists.balances||[]).find(p=>String(p.id)===String(data.balance_id));
 function select(label,key,items,display,required=true){return <label>{label}<select aria-label={label} value={data[key]||""} required={required} disabled={!!pending} onChange={e=>set(key,e.target.value)}><option value="">Choose {label.toLowerCase()}</option>{items.map(p=><option key={p.id} value={p.id}>{display(p)}</option>)}</select></label>}
 function text(label,key,type="text",required=true){return <label>{label}<input aria-label={label} type={type} min={type==="number"?1:undefined} maxLength={key==="device_name"?200:key==="serial_raw"?200:500} required={required} disabled={!!pending} value={data[key]||""} onChange={e=>set(key,e.target.value)}/></label>}
 function prepare(e){e.preventDefault();setError("");setErrors(null);setResult(null);
 try{
 const body={operation_key:crypto.randomUUID(),reason:data.reason,external_reference:data.external_reference||""};
 if(action==="receive")Object.assign(body,{product_model_id:Number(data.product_model_id),destination_location_id:Number(data.destination_location_id),condition:data.condition,state:data.state,quantity:Number(data.quantity)});
 if(["transfer","issue"].includes(action)){
  if(!asset&&!balance)throw new Error("Select an asset or balance.");
  Object.assign(body,asset?{asset_id:asset.id,quantity:1,source_location_id:asset.current_location_id,source_condition:asset.condition,source_state:asset.lifecycle_status}:{product_model_id:balance.product_model_id,quantity:Number(data.quantity),source_location_id:balance.location_id,source_condition:balance.condition,source_state:balance.stock_state});
  if(action==="transfer")Object.assign(body,{destination_location_id:Number(data.destination_location_id),condition:body.source_condition,state:body.source_state});
  else body.recipient_id=Number(data.recipient_id);
 }
 if(action==="return"){
  if(!assignment)throw new Error("Select a current assignment.");
  Object.assign(body,{asset_id:assignment.asset_id,assignment_id:assignment.id,destination_location_id:Number(data.destination_location_id),condition:data.condition,state:data.state});
 }
 setPending({action,body});
 }catch(e){setError(e.message);}
 }
 async function post(){setBusy(true);setError("");setErrors(null);try{const response=await api.save("/api/transactions/manual/"+pending.action+"/","POST",pending.body);setResult(response);setPending(null);setData({});setRevision(r=>r+1);}catch(e){setErrors(e.details||null);setError(e.message+" Retry uses the same operation key and unchanged values.");}finally{setBusy(false);}}
 const destinations=(lists.locations||[]).filter(l=>l.is_active&&String(l.warehouse_id)===String(data.warehouse_id));
 const products=(lists.products||[]).filter(p=>p.is_active&&p.tracking_mode===(action==="receive"?"BULK":"SERIALIZED")&&(!category||String(p.category)===category)&&(!manufacturer||String(p.manufacturer)===manufacturer));
 return <section className="panel">
 <div className="toolbar">{Object.keys(capabilities).filter(permitted).map(a=><button key={a} disabled={!!pending||registrationState.busy||registrationState.pending} onClick={()=>{setAction(a);setData({});setResult(null);setError("");}}>{({register:"Register New Asset",receive:"Receive Bulk Stock",transfer:"Transfer Stock",issue:"Issue Equipment",return:"Return Equipment"})[a]}</button>)}</div>
 {error&&<p role="alert" className="notice error">{error}</p>}
 {errors&&<div role="alert">{errorMessages(errors).map((s,i)=><p key={i}>{s}</p>)}</div>}
 {result&&<div role="status">Posted operation {result.operation_key}. Movements: {result.movement_ids.join(", ")}. Assets: {result.assets?.map(a=>a.asset_tag).join(", ")||result.asset_ids.join(", ")||"Bulk inventory"}. {result.receipt?.map(r=><p key={r.id}>Receipt {r.public_id} ? {r.operation_type} ? {r.recorded_at}</p>)} {result.warnings.map(w=><p key={w}>{w}</p>)}</div>}
 {!Object.keys(capabilities).some(permitted)&&<p>Read-only inventory activity. No stock posting permissions.</p>}
 {action==="register"&&permitted(action)&&<SerializedAssetRegistration user={user} onSuccess={()=>setRevision(r=>r+1)} onStateChange={setRegistrationState}/>}
 {action!=="register"&&permitted(action)&&<form onSubmit={prepare} className="master-form">
 <h2>{action==="receive"?"Receive Bulk Stock":action==="transfer"?"Transfer Stock":action==="issue"?"Issue Equipment":"Return Equipment"}</h2>
 {action==="receive"&&<>
 <label>Category filter<select aria-label="Category filter" disabled={!!pending} value={category} onChange={e=>{setCategory(e.target.value);set("product_model_id","")}}><option value="">All categories</option>{(lists.categories||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
 <label>Manufacturer filter<select aria-label="Manufacturer filter" disabled={!!pending} value={manufacturer} onChange={e=>{setManufacturer(e.target.value);set("product_model_id","")}}><option value="">All manufacturers</option>{(lists.manufacturers||[]).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
 {select("Product model","product_model_id",products,p=>p.sku_code+" — "+p.name)}
 <p><a href="#/products">Create or edit a product model</a> using your catalog permissions.</p>
 {product&&<p>Catalog specifications: {JSON.stringify(Object.fromEntries(Object.entries(product).filter(([k,v])=>["model_number","part_number","capacity_bytes","memory_generation","interface_type","speed_value","speed_unit","size_value","size_unit","port_count"].includes(k)&&v)))}</p>}
 </>}

 {["transfer","issue"].includes(action)&&<>
 {select("Asset","asset_id",(lists.assets||[]).filter(a=>a.lifecycle_status==="AVAILABLE"||(action==="transfer"&&a.lifecycle_status==="QUARANTINED")),p=>p.asset_tag+" — "+p.device_name,action==="issue")}
 {action==="transfer"&&!data.asset_id&&select("Bulk source balance","balance_id",(lists.balances||[]).filter(b=>b.quantity>0),p=>"Product "+p.product_model_id+" / location "+p.location_id+" / "+p.condition+" / "+p.stock_state+" / "+p.quantity)}
 {asset&&<p>Source: location {asset.current_location_id}, {asset.condition}, {asset.lifecycle_status}.</p>}
 </>}
 {action==="return"&&select("Current assignment","assignment_id",lists.assignments||[],p=>"Assignment "+p.id+" / asset "+p.asset_id+" / recipient "+p.recipient_id)}
 {(action==="receive"||(action==="transfer"&&!data.asset_id))&&text("Quantity in pieces","quantity","number")}
 {action==="issue"&&select("Recipient","recipient_id",lists.recipients||[],p=>p.name+" ("+p.code+")")}
 {action!=="issue"&&<>{select("Destination warehouse","warehouse_id",(lists.warehouses||[]).filter(w=>w.is_active),p=>p.name)}{select("Destination location","destination_location_id",destinations,p=>p.name+" ("+p.code+")")}</>}
 {["receive","return"].includes(action)&&<>
 {select("Condition","condition",["NEW","USED","REFURBISHED","BROKEN","UNKNOWN"].map(id=>({id})),p=>p.id)}
 {select("Stock state","state",["AVAILABLE","QUARANTINED"].map(id=>({id})),p=>p.id)}
 </>}
 {text("Reason / remarks","reason")}{text("External reference (optional)","external_reference","text",false)}
 {!pending&&<button type="submit">Review transaction</button>}
 </form>}
 {pending&&<section role="dialog" aria-label="Confirm stock transaction"><h3>Confirm stock transaction</h3><pre>{JSON.stringify(pending.body,null,2)}</pre><button disabled={busy} onClick={post}>{busy?"Posting…":"Confirm and post"}</button><button disabled={busy} onClick={()=>{if(window.confirm("Cancel this pending request? If a response was lost, verify activity before posting a new operation."))setPending(null)}}>Cancel pending request</button></section>}
 <h2>Inventory Activity</h2>
 <button disabled={busy} onClick={()=>setRevision(r=>r+1)}>Refresh activity</button>
 <table><thead><tr>{["Time","Action","Operator","Asset / product","From","To","Quantity"].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{(lists.movements||[]).map(m=><tr key={m.id}><td>{m.recorded_at}</td><td>{m.operation_type}</td><td>{m.operator}</td><td>{m.asset_id?"Asset "+m.asset_id:"Product "+m.product_model_id}</td><td>{m.source_location_id||"—"}</td><td>{m.destination_location_id||"—"}</td><td>{m.quantity}</td></tr>)}</tbody></table>
 <p>Bulk issue/return custody is not available on this page. Acquisition cost, historical registration dates and workbook imports are not supported by this workflow.</p>
 </section>;
}
