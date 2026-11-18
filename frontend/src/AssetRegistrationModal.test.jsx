import React from "react";
import {afterEach,beforeEach,expect,test,vi} from "vitest";
import {act,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import App from "./App";
import {InventoryOperations} from "./InventoryOperations";
import {api,request} from "./api";
vi.mock("./api",async importOriginal=>{
 const actual=await importOriginal();
 return {...actual,api:{me:vi.fn(),save:vi.fn(),login:vi.fn(),logout:vi.fn()},request:vi.fn()};
});
const user={username:"operator",manual_inventory_enabled:true,master_data_delete_enabled:false,permissions:[
 "inventory.view_asset","inventory.add_asset","inventory.view_productmodel","inventory.view_assetcategory","inventory.view_manufacturer",
 "warehouse.view_warehouse","warehouse.view_storagelocation","transactions.receive_stock"
]};
const receipt={operation_key:"posted-key",movement_ids:[7],asset_ids:[9],assets:[{id:9,asset_tag:"AST-MODAL"}],
 receipt:[{id:7,public_id:"receipt-modal",recorded_at:"2026-11-17",operation_type:"STOCK_IN"}],warnings:[]};
let registered;
beforeEach(()=>{
 vi.resetAllMocks();vi.spyOn(window,"confirm").mockReturnValue(true);window.location.hash="#/assets";registered=false;
 api.me.mockResolvedValue({user});api.save.mockImplementation(async()=>{registered=true;return receipt});
 request.mockImplementation(async url=>{
  let results=[];
  if(url.includes("product-models"))results=[{id:1,sku_code:"SER",name:"Serialized model",tracking_mode:"SERIALIZED",is_active:true,category:1,manufacturer:2},{id:2,sku_code:"BULK",name:"Bulk model",tracking_mode:"BULK",is_active:true},{id:3,sku_code:"OLD",name:"Inactive model",tracking_mode:"SERIALIZED",is_active:false}];
  else if(url.includes("/warehouses"))results=[{id:4,name:"Site",is_active:true}];
  else if(url.includes("/locations"))results=[{id:5,name:"Bin",code:"BIN",warehouse_id:4,is_active:true},{id:6,name:"Other site",warehouse_id:99,is_active:true}];
  else if(url.includes("/categories"))results=[{id:1,name:"Equipment"}];
  else if(url.includes("/manufacturers"))results=[{id:2,name:"Manufacturer"}];
  else if(url.includes("/inventory/assets")&&registered)results=[{id:9,asset_tag:"AST-MODAL",device_name:"Device",product_name:"Serialized model",condition:"USED",lifecycle_status:"AVAILABLE",location_name:"Bin"}];
  return {results,next:null,previous:null,count:results.length};
 });
});
afterEach(()=>vi.restoreAllMocks());
async function open(){
 const rendered=render(<App/>);const trigger=await screen.findByRole("button",{name:"Register asset"});trigger.focus();fireEvent.click(trigger);
 const dialog=await screen.findByRole("dialog",{name:"Register asset"});
 await within(dialog).findByRole("option",{name:/SER.*Serialized model/});
 return {...rendered,trigger,dialog};
}
function fill(dialog){
 for(const [label,value] of [["Product model","1"],["Device name","Device"],["Serial number (optional)","00123"],["Destination warehouse","4"],["Destination location","5"],["Condition","USED"],["Stock state","AVAILABLE"],["Reason / remarks","Manual receipt"]]){
  fireEvent.change(within(dialog).getByLabelText(label),{target:{value}});
 }
}
function review(dialog){fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));}
test("Assets registration opens an accessible modal and never changes the URL",async()=>{
 const {dialog,container}=await open();
 expect(window.location.hash).toBe("#/assets");expect(dialog).toHaveAttribute("aria-modal","true");expect(container).toHaveAttribute("inert");
 expect(within(dialog).queryByRole("option",{name:/Bulk model/})).not.toBeInTheDocument();
 expect(within(dialog).queryByRole("option",{name:/Inactive model/})).not.toBeInTheDocument();
 expect(screen.queryByText(/Phase 4B will not create/)).not.toBeInTheDocument();
});
test.each(["Close registration","Cancel","Escape"])("%s dismisses a pristine modal and restores focus without navigation",async control=>{
 const {dialog,trigger,container}=await open();
 if(control==="Escape")fireEvent.keyDown(document,{key:"Escape"});else fireEvent.click(within(dialog).getByRole("button",{name:control}));
 await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
 expect(window.location.hash).toBe("#/assets");expect(trigger).toHaveFocus();expect(container).not.toHaveAttribute("inert");expect(window.confirm).not.toHaveBeenCalled();
});
test("dirty close requires confirmation and preserves edits when declined",async()=>{
 const {dialog}=await open();fireEvent.change(within(dialog).getByLabelText("Device name"),{target:{value:"Unsaved"}});
 window.confirm.mockReturnValueOnce(false);fireEvent.click(within(dialog).getByRole("button",{name:"Close registration"}));
 expect(dialog).toBeInTheDocument();expect(within(dialog).getByLabelText("Device name")).toHaveValue("Unsaved");
 expect(window.confirm).toHaveBeenCalledWith("Discard unsaved registration changes?");
 fireEvent.keyDown(document,{key:"Escape"});await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
 expect(window.location.hash).toBe("#/assets");
});
test("Tab and Shift+Tab wrap inside the modal",async()=>{
 const {dialog}=await open();const cancel=within(dialog).getByRole("button",{name:"Review registration"}),close=within(dialog).getByRole("button",{name:"Close registration"});
 cancel.focus();fireEvent.keyDown(document,{key:"Tab"});expect(close).toHaveFocus();
 fireEvent.keyDown(document,{key:"Tab",shiftKey:true});expect(cancel).toHaveFocus();
});
test("search and filters survive opening and dismissing registration",async()=>{
 render(<App/>);const trigger=await screen.findByRole("button",{name:"Register asset"});
 fireEvent.change(screen.getByLabelText("Search Assets"),{target:{value:"kept search"}});
 fireEvent.change(screen.getByLabelText("Filter"),{target:{value:"AVAILABLE"}});
 await waitFor(()=>expect(request.mock.calls.some(([url])=>url.includes("search=kept+search")&&url.includes("lifecycle_status=AVAILABLE"))).toBe(true));
 fireEvent.click(trigger);await screen.findByRole("dialog");fireEvent.keyDown(document,{key:"Escape"});
 await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
 expect(screen.getByLabelText("Search Assets")).toHaveValue("kept search");expect(screen.getByLabelText("Filter")).toHaveValue("AVAILABLE");expect(window.location.hash).toBe("#/assets");
});
test("success uses Phase 4C API, shows tag/receipt and refreshes Assets without closing",async()=>{
 const {dialog}=await open();fill(dialog);review(dialog);
 expect(api.save).not.toHaveBeenCalled();fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 expect(await within(dialog).findByRole("status")).toHaveTextContent("AST-MODAL");
 expect(within(dialog).getByText(/Receipt receipt-modal/)).toBeInTheDocument();
 expect(api.save.mock.calls[0][0]).toBe("/api/transactions/manual/register/");
 expect(api.save.mock.calls[0][1]).toBe("POST");expect(api.save.mock.calls[0][2].serial_raw).toBe("00123");
 expect(api.save.mock.calls[0][2]).not.toHaveProperty("asset_tag");
 expect(request.mock.calls.filter(([url])=>url.includes("/inventory/assets")).length).toBeGreaterThan(1);
 expect(dialog).toBeInTheDocument();expect(window.location.hash).toBe("#/assets");
 await waitFor(()=>expect(within(dialog).getByRole("button",{name:"Close registration"})).not.toBeDisabled());
 fireEvent.click(within(dialog).getByRole("button",{name:"Close registration"}));
 await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
 expect(screen.getByRole("cell",{name:"AST-MODAL"})).toBeInTheDocument();
 expect(window.confirm).not.toHaveBeenCalled();
});
test("validation errors stay in the modal and allow correction",async()=>{
 api.save.mockRejectedValueOnce({status:400,message:"Invalid registration",details:{device_name:["Use a meaningful name"]}});
 const {dialog}=await open();fill(dialog);review(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 await within(dialog).findByText("Device name: Use a meaningful name");
 expect(dialog).toBeInTheDocument();expect(window.location.hash).toBe("#/assets");
 const name=within(dialog).getByLabelText("Device name");expect(name).toHaveAttribute("aria-invalid","true");expect(name).not.toBeDisabled();
 fireEvent.change(name,{target:{value:"Corrected device"}});review(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 await within(dialog).findByText(/Receipt receipt-modal/);expect(api.save).toHaveBeenCalledTimes(2);
});
test("duplicate clicks are single-flight and closing is blocked while posting",async()=>{
 let finish;api.save.mockImplementation(()=>new Promise(resolve=>{finish=resolve}));
 const {dialog}=await open();fill(dialog);review(dialog);const button=within(dialog).getByRole("button",{name:"Confirm & register"});
 fireEvent.click(button);fireEvent.click(button);
 expect(api.save).toHaveBeenCalledTimes(1);expect(within(dialog).getByRole("button",{name:"Close registration"})).toBeDisabled();
 fireEvent.keyDown(document,{key:"Escape"});expect(dialog).toBeInTheDocument();
 await act(async()=>{registered=true;finish(receipt)});await within(dialog).findByText(/Receipt receipt-modal/);
 expect(api.save).toHaveBeenCalledTimes(1);
});
test("uncertain retry preserves the exact operation key and payload",async()=>{
 api.save.mockRejectedValueOnce(new Error("Connection lost"));
 const {dialog}=await open();fill(dialog);review(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 await within(dialog).findByText(/Retry this registration/);const first=api.save.mock.calls[0][2];
 expect(within(dialog).queryByLabelText("Device name")).not.toBeInTheDocument();
 expect(within(dialog).getByRole("heading",{name:"Review asset registration"})).toBeInTheDocument();
 fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));await within(dialog).findByText(/Receipt receipt-modal/);
 expect(api.save.mock.calls[1][2]).toEqual(first);
});
test("feature-disabled modal cannot post or render legacy registration",async()=>{
 api.me.mockResolvedValue({user:{...user,manual_inventory_enabled:false}});
 render(<App/>);fireEvent.click(await screen.findByRole("button",{name:"Register asset"}));
 const dialog=await screen.findByRole("dialog");expect(within(dialog).getByRole("alert")).toHaveTextContent(/registration is disabled/);
 expect(within(dialog).queryByRole("button",{name:"Review registration"})).not.toBeInTheDocument();expect(api.save).not.toHaveBeenCalled();
});
test("Inventory Operations continues to use the same serialized registration component",async()=>{
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:/SER.*Serialized model/});
 const form=screen.getByRole("heading",{name:"Register New Asset"}).closest("section");fill(form);review(form);
 fireEvent.click(within(form).getByRole("button",{name:"Confirm & register"}));await screen.findByText(/Receipt receipt-modal/);
 expect(api.save.mock.calls[0][0]).toBe("/api/transactions/manual/register/");
 expect(screen.getByRole("button",{name:"Register another asset"})).toBeInTheDocument();
});
