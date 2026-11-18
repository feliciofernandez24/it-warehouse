import React,{useId,useLayoutEffect,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {SerializedAssetRegistration,canRegisterAsset} from "./SerializedAssetRegistration";
import {EquipmentIcon,RegistrationProgress} from "./RegistrationPresentation";

export function AssetRegistrationModal({user,onClose,onSuccess}) {
 const [host]=useState(()=>document.createElement("div"));
 const [state,setState]=useState({busy:false,pending:false,dirty:false,step:"details",loading:true,canSubmit:false});
 const dialog=useRef(null),form=useRef(null),closeButton=useRef(null),close=useRef(onClose);
 const title=useId();close.current=onClose;
 function dismiss(){
  const current=form.current?.getCloseState()||{};
  if(current.busy)return;
  if(current.uncertain){
   if(!window.confirm("Registration may already have completed. Check Inventory Activity before starting another registration. Close this form?"))return;
  }else if(current.dirty&&!window.confirm("Discard unsaved registration changes?"))return;
  close.current();
 }
 const dismissRef=useRef(dismiss);dismissRef.current=dismiss;
 useLayoutEffect(()=>{
  const previous=document.activeElement,overflow=document.body.style.overflow;
  host.dataset.assetRegistrationModal="true";document.body.appendChild(host);
  const siblings=Array.from(document.body.children).filter(node=>node!==host).map(node=>({node,inert:node.getAttribute("inert"),hidden:node.getAttribute("aria-hidden")}));
  siblings.forEach(({node})=>{node.setAttribute("inert","");node.setAttribute("aria-hidden","true");});
  document.body.style.overflow="hidden";closeButton.current?.focus();
  function keyboard(e){
   if(e.key==="Escape"){e.preventDefault();e.stopPropagation();dismissRef.current();return;}
   if(e.key!=="Tab")return;
   const controls=Array.from(dialog.current?.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),a[href],[tabindex="0"]')||[]).filter(node=>!node.closest("[hidden]"));
   const first=controls[0],last=controls[controls.length-1];
   if(!first){e.preventDefault();dialog.current?.focus();return;}
   if(e.shiftKey&&(document.activeElement===first||!dialog.current.contains(document.activeElement))){e.preventDefault();last.focus();}
   else if(!e.shiftKey&&(document.activeElement===last||!dialog.current.contains(document.activeElement))){e.preventDefault();first.focus();}
  }
  document.addEventListener("keydown",keyboard,true);
  return()=>{
   document.removeEventListener("keydown",keyboard,true);document.body.style.overflow=overflow;
   siblings.forEach(({node,inert,hidden})=>{if(inert===null)node.removeAttribute("inert");else node.setAttribute("inert",inert);if(hidden===null)node.removeAttribute("aria-hidden");else node.setAttribute("aria-hidden",hidden);});
   host.remove();if(previous?.isConnected)previous.focus?.();
  };
 },[host]);
 return createPortal(<div className="editor-backdrop asset-registration-backdrop">
  <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby={title} tabIndex={-1} className="asset-registration-modal">
   <header className="asset-registration-header">
    <div className="registration-header-main"><span className="registration-header-icon"><EquipmentIcon/></span><div className="registration-header-copy"><span className="eyebrow">IT WAREHOUSE / ASSET MANAGEMENT</span><h2 id={title}>Register asset</h2><p>{state.step==="review"?"Confirm the receiving details before registration.":state.step==="success"?"Your equipment has been added to inventory.":"Add equipment and its initial stock receipt."}</p></div><button ref={closeButton} className="registration-close" type="button" disabled={state.busy} onClick={dismiss} aria-label="Close registration"><span aria-hidden="true"><EquipmentIcon kind="close"/></span><span>Close</span></button></div>
    <RegistrationProgress step={state.step}/>
   </header>
   <div className="asset-registration-body" aria-busy={state.busy}>
    <SerializedAssetRegistration ref={form} user={user} onSuccess={onSuccess} onStateChange={setState} autoFocus allowAnother={false} embedded externalActions/>
   </div>
   <footer className="asset-registration-footer">
    <div className="registration-footer-context">{state.step==="review"?<button className="registration-back" type="button" disabled={state.busy} onClick={()=>form.current?.back()}>Back to edit</button>:<span>{state.step==="success"?"Registration complete":<>Required fields are marked <b>*</b></>}</span>}</div>
    <div className="registration-footer-actions">
     {state.step!=="success"&&<button type="button" disabled={state.busy} onClick={dismiss}>Cancel</button>}
     {!canRegisterAsset(user)?null:state.step==="success"?<button className="primary" type="button" onClick={dismiss}>Back to Assets</button>:state.step==="review"?<button className="primary" type="button" disabled={state.busy} onClick={()=>form.current?.confirm()}>{state.busy?"Registering…":"Confirm & register"}</button>:<button className="primary" type="button" disabled={!state.canSubmit||state.busy} onClick={()=>form.current?.review()}>Review registration</button>}
    </div>
   </footer>
  </section>
 </div>,host);
}
