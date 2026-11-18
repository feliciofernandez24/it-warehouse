import React,{useEffect,useState} from "react";
import {api,request,errorMessages} from "./api";
import {management,canManage} from "./MasterData";
export const canDelete=(user,page)=>page!=="assets"&&Boolean(management[page])&&user.master_data_delete_enabled===true&&canManage(user,page,"delete");

export function MasterDelete({page,row,user,onClose,onDeleted,onDeactivate}) {
 const [record,setRecord]=useState(null),[reason,setReason]=useState(""),[busy,setBusy]=useState(false),[errors,setErrors]=useState(null);
 useEffect(()=>{let active=true;request("/api/management/"+management[page].endpoint+"/"+row.id+"/").then(r=>active&&setRecord(r)).catch(e=>active&&setErrors(e.details||{detail:e.message}));return()=>{active=false};},[page,row.id]);
 async function submit(e){e.preventDefault();if(!canDelete(user,page)||!record||busy)return;setBusy(true);setErrors(null);
 try{await api.remove("/api/management/"+management[page].endpoint+"/"+row.id+"/",{expected_version:record.version,change_reason:reason});onDeleted("Deleted "+management[page].singular+".");}catch(e){setErrors(e.details||{detail:e.message});}finally{setBusy(false);}
 }
 return <div className="editor-backdrop"><section className="master-editor" role="dialog" aria-modal="true" aria-label="Confirm master deletion">
 <h2>Delete {management[page].singular}</h2><p>{row.name||row.sku_code||row.code} (ID {row.id}). This permanently removes an unused record; its audit entry is retained.</p>
 {errors&&<div role="alert">{errorMessages(errors).map((s,i)=><p key={i}>{s}</p>)}</div>}
 <form onSubmit={submit}><label>Reason for deletion<input aria-label="Reason for deletion" required maxLength={500} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
 <button type="button" disabled={busy} onClick={onClose}>Cancel</button>
 {onDeactivate&&<button type="button" disabled={busy} onClick={onDeactivate}>Edit / deactivate instead</button>}
 <button type="submit" disabled={busy||!record||!canDelete(user,page)}>{busy?"Deleting…":"Confirm deletion"}</button></form>
 </section></div>;
}
