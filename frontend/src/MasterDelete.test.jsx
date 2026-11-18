import React from "react";
import {beforeEach,expect,test,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import App from "./App";
import {MasterDelete,canDelete} from "./MasterDelete";
import {MasterEditor} from "./MasterData";
import {InventoryOperations} from "./InventoryOperations";
import {api,request} from "./api";
vi.mock("./api",async importOriginal=>{const original=await importOriginal();return {...original,api:{me:vi.fn(),save:vi.fn(),remove:vi.fn(),login:vi.fn(),logout:vi.fn()},request:vi.fn()}});
const user={username:"admin",manual_inventory_enabled:true,master_data_delete_enabled:true,permissions:["inventory.view_assetcategory","inventory.delete_assetcategory","inventory.change_assetcategory","inventory.view_asset","inventory.add_asset","inventory.view_productmodel","warehouse.view_warehouse","warehouse.view_storagelocation","transactions.receive_stock"]};
beforeEach(()=>{vi.resetAllMocks();window.location.hash="#/categories";api.me.mockResolvedValue({user});api.remove.mockResolvedValue(null);request.mockImplementation(async url=>url.includes("/management/categories/1/")?{id:1,name:"Unused category",version:7}:{results:[],next:null,count:0});});
test("deletion requires delete permission and enabled deployment",()=>{
 expect(canDelete(user,"categories")).toBe(true);
 expect(canDelete({...user,master_data_delete_enabled:false},"categories")).toBe(false);
 expect(canDelete({...user,permissions:["inventory.view_assetcategory"]},"categories")).toBe(false);
 expect(canDelete(user,"assets")).toBe(false);
});
test("confirmation identifies target and sends version and reason",async()=>{
 const done=vi.fn();render(<MasterDelete page="categories" row={{id:1,name:"Unused category"}} user={user} onClose={vi.fn()} onDeleted={done}/>);
 expect(screen.getByText(/Unused category \(ID 1\)/)).toBeInTheDocument();
 await waitFor(()=>expect(screen.getByRole("button",{name:"Confirm deletion"})).not.toBeDisabled());
 expect(api.remove).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText("Reason for deletion"),{target:{value:"Duplicate unused category"}});
 fireEvent.click(screen.getByRole("button",{name:"Confirm deletion"}));
 await waitFor(()=>expect(done).toHaveBeenCalledWith("Deleted category."));
 expect(api.remove).toHaveBeenCalledWith("/api/management/categories/1/",{expected_version:7,change_reason:"Duplicate unused category"});
});
test("dependency errors remain visible with deactivation alternative",async()=>{
 api.remove.mockRejectedValue({details:{dependencies:["Referenced by product models. Deactivate instead."]}});
 const deactivate=vi.fn();render(<MasterDelete page="categories" row={{id:1,name:"Used"}} user={user} onClose={vi.fn()} onDeleted={vi.fn()} onDeactivate={deactivate}/>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Confirm deletion"})).not.toBeDisabled());
 fireEvent.change(screen.getByLabelText("Reason for deletion"),{target:{value:"Unused?"}});fireEvent.click(screen.getByRole("button",{name:"Confirm deletion"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("Referenced by product models");
 fireEvent.click(screen.getByRole("button",{name:"Edit / deactivate instead"}));expect(deactivate).toHaveBeenCalled();
});
test("catalog delete action refreshes after success",async()=>{
 let removed=false;api.remove.mockImplementation(async()=>{removed=true});
 request.mockImplementation(async url=>url.includes("/management/categories/1/")?{id:1,version:0,name:"Unused"}:{results:removed?[]:[{id:1,code:"UNUSED",name:"Unused",is_active:true}],count:removed?0:1,next:null});
 render(<App/>);fireEvent.click(await screen.findByRole("button",{name:"Delete category"}));
 await waitFor(()=>expect(screen.getByRole("button",{name:"Confirm deletion"})).not.toBeDisabled());
 fireEvent.change(screen.getByLabelText("Reason for deletion"),{target:{value:"Unused"}});fireEvent.click(screen.getByRole("button",{name:"Confirm deletion"}));
 await screen.findByText("No categories found");expect(screen.getByRole("status")).toHaveTextContent("Deleted category");
});
test("assets register button opens Phase 4C modal without redirect",async()=>{
 window.location.hash="#/assets";render(<App/>);
 fireEvent.click(await screen.findByRole("button",{name:"Register asset"}));
 // jsdom does not synchronously dispatch hashchange.
 fireEvent(window,new Event("hashchange"));
 await screen.findByRole("heading",{name:"Register asset"});
 expect(window.location.hash).toBe("#/assets");
 expect(screen.getByRole("dialog",{name:"Register asset"})).toBeInTheDocument();
 expect(screen.queryByText(/Phase 4B will not create/)).not.toBeInTheDocument();
});
test("standalone asset editor respects enabled receipt workflow",()=>{
 render(<MasterEditor page="assets" user={user} onClose={vi.fn()} onSaved={vi.fn()}/>);
 expect(screen.getByRole("heading",{name:"Register asset"})).toBeInTheDocument();
 expect(screen.queryByText(/Registration is unavailable/)).not.toBeInTheDocument();
});
test("disabled manual feature stays fail-closed without legacy form",()=>{
 render(<MasterEditor page="assets" user={{...user,manual_inventory_enabled:false}} onClose={vi.fn()} onSaved={vi.fn()}/>);
 expect(screen.getByRole("alert")).toHaveTextContent(/registration is disabled/);
 expect(screen.queryByText(/Phase 4B will not create/)).not.toBeInTheDocument();
 expect(screen.queryByRole("button",{name:"Review registration"})).not.toBeInTheDocument();
});
test("successful receipt shows generated tag and actual receipt identifier",async()=>{
 api.save.mockResolvedValue({operation_key:"op",movement_ids:[7],asset_ids:[9],assets:[{id:9,asset_tag:"AST-GENERATED"}],receipt:[{id:7,public_id:"receipt-uuid",operation_type:"STOCK_IN",recorded_at:"2026-11-17"}],warnings:[]});
 request.mockImplementation(async url=>({results:url.includes("product-models")?[{id:1,sku_code:"SER",name:"Model",tracking_mode:"SERIALIZED",is_active:true}]:url.includes("/warehouses")?[{id:2,name:"Site",is_active:true}]:url.includes("/locations")?[{id:3,name:"Area",warehouse_id:2,is_active:true}]:[],next:null,count:1}));
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Model"});
 for(const [label,value] of [["Product model","1"],["Device name","Device"],["Destination warehouse","2"],["Destination location","3"],["Condition","USED"],["Stock state","AVAILABLE"],["Reason / remarks","Receive"]])fireEvent.change(screen.getByLabelText(label),{target:{value}});
 fireEvent.click(screen.getByRole("button",{name:"Review registration"}));fireEvent.click(screen.getByRole("button",{name:"Confirm & register"}));
 expect(await screen.findByRole("status")).toHaveTextContent("AST-GENERATED");
 expect(screen.getByText(/Receipt receipt-uuid/)).toBeInTheDocument();
});
test("manual form renders field-level server validation",async()=>{
 api.save.mockRejectedValue({message:"Invalid",details:{device_name:["Required name"],condition:["Choose condition"]}});
 // Reuse a validated form submission to inspect the structured error rather than invent success.
 request.mockImplementation(async url=>({results:url.includes("product-models")?[{id:1,sku_code:"SER",name:"Model",tracking_mode:"SERIALIZED",is_active:true}]:[],next:null}));
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Model"});
 fireEvent.submit(document.querySelector(".registration-form"));fireEvent.click(screen.getByRole("button",{name:"Confirm & register"}));
 expect(await screen.findByText("Device name: Required name")).toBeInTheDocument();
 expect(screen.getByText("Condition: Choose condition")).toBeInTheDocument();
});
