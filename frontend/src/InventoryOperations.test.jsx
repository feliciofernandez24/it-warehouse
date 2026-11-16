import React from "react";
import {beforeEach,expect,test,vi} from "vitest";
import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import App from "./App";
import {InventoryOperations} from "./InventoryOperations";
import {api,request} from "./api";
vi.mock("./api",()=>({api:{save:vi.fn(),me:vi.fn()},request:vi.fn()}));
const user={permissions:["transactions.receive_stock","transactions.transfer_stock","transactions.issue_stock","transactions.return_stock","transactions.view_stockmovement","transactions.view_assetassignment","inventory.view_productmodel","inventory.view_asset","inventory.view_stockbalance","warehouse.view_storagelocation","warehouse.view_warehouse","inventory.view_assetcategory","inventory.view_manufacturer","accounts.view_assetrecipient"]};
const lists={
 "management/product-models":[{id:1,sku_code:"SER",name:"Serial model",tracking_mode:"SERIALIZED",is_active:true,category:1,manufacturer:1},{id:2,sku_code:"BULK",name:"Bulk model",tracking_mode:"BULK",is_active:true,category:1}],
 "inventory/assets":[{id:5,asset_tag:"AST-TEST",device_name:"Device",current_location_id:7,condition:"USED",lifecycle_status:"AVAILABLE"}],
 locations:[{id:7,warehouse_id:4,name:"Area",code:"AREA",is_active:true}],
 warehouses:[{id:4,name:"Site",is_active:true}],
 "inventory/categories":[{id:1,name:"Category"}],"inventory/manufacturers":[{id:1,name:"Manufacturer"}],
 "transactions/recipients":[{id:3,code:"REC",name:"Person"}],
 "transactions/assignments":[{id:9,asset_id:5,recipient_id:3}],
 "transactions/balances":[{id:8,product_model_id:2,location_id:7,condition:"NEW",stock_state:"AVAILABLE",quantity:6}],
 "transactions/movements":[{id:1,operation_type:"STOCK_IN",operator:"operator",recorded_at:"2026-11-16",quantity:1,asset_id:5}]
};
beforeEach(()=>{vi.resetAllMocks();request.mockImplementation(async url=>{const path=url.split("?")[0].replace("/api/","").replace(/\/$/,"");return {results:lists[path]||[],next:null};});api.save.mockResolvedValue({operation_key:"posted",movement_ids:[1],asset_ids:[5],warnings:[]});});
const change=(label,value)=>fireEvent.change(screen.getByLabelText(label),{target:{value}});
async function register(){
 render(<InventoryOperations user={user}/>);
 await screen.findByRole("option",{name:"SER — Serial model"});
 change("Product model","1");change("Device name","Named equipment");change("Serial number (optional)","00123");
 change("Destination warehouse","4");change("Destination location","7");change("Condition","USED");change("Stock state","AVAILABLE");change("Reason / remarks","Manual receipt");
 fireEvent.click(screen.getByRole("button",{name:"Review transaction"}));
}
test("registration confirms before posting and shows actual API result",async()=>{
 await register();expect(api.save).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Confirm and post"}));
 await screen.findByText(/Posted operation posted/);
 const [url,method,body]=api.save.mock.calls[0];expect(url).toBe("/api/transactions/manual/register/");expect(method).toBe("POST");expect(body.serial_raw).toBe("00123");expect(body).not.toHaveProperty("asset_tag");
});
test("uncertain failure retains identical operation key and payload",async()=>{
 api.save.mockRejectedValueOnce(new Error("Unavailable"));
 await register();fireEvent.click(screen.getByRole("button",{name:"Confirm and post"}));
 await screen.findByRole("alert");
 fireEvent.click(screen.getByRole("button",{name:"Confirm and post"}));
 await screen.findByText(/Posted operation posted/);
 expect(api.save.mock.calls[0][2]).toEqual(api.save.mock.calls[1][2]);
});
test("viewer cannot see posting controls",async()=>{
 render(<InventoryOperations user={{permissions:["transactions.view_stockmovement"]}}/>);
 expect(screen.queryByRole("button",{name:"Register New Asset"})).not.toBeInTheDocument();
 await screen.findByText("operator");
});
test("bulk mode shows only BULK products and explicit quantity",async()=>{
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Serial model"});
 fireEvent.click(screen.getByRole("button",{name:"Receive Bulk Stock"}));
 expect(screen.getByLabelText("Quantity in pieces")).toBeInTheDocument();
 expect(screen.queryByRole("option",{name:"SER — Serial model"})).not.toBeInTheDocument();
 expect(screen.getByRole("option",{name:"BULK — Bulk model"})).toBeInTheDocument();
});
test("transfer supports asset and bulk source selection",async()=>{
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Serial model"});
 fireEvent.click(screen.getByRole("button",{name:"Transfer Stock"}));
 expect(screen.getByLabelText("Asset")).toBeInTheDocument();expect(screen.getByLabelText("Bulk source balance")).toBeInTheDocument();
 change("Asset","5");expect(screen.queryByLabelText("Quantity in pieces")).not.toBeInTheDocument();
 expect(screen.getByText(/Source: location 7/)).toBeInTheDocument();
});
test("issue uses actual recipient options",async()=>{
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Serial model"});
 fireEvent.click(screen.getByRole("button",{name:"Issue Equipment"}));
 expect(screen.getByRole("option",{name:"Person (REC)"})).toBeInTheDocument();
 expect(screen.queryByLabelText("Destination location")).not.toBeInTheDocument();
});
test("return requires current assignment",async()=>{
 render(<InventoryOperations user={user}/>);await screen.findByRole("option",{name:"SER — Serial model"});
 fireEvent.click(screen.getByRole("button",{name:"Return Equipment"}));
 expect(screen.getByRole("option",{name:"Assignment 9 / asset 5 / recipient 3"})).toBeInTheDocument();
 expect(screen.getByLabelText("Current assignment")).toBeRequired();
});
test("load failure is visible without fabricated success",async()=>{
 request.mockRejectedValue(new Error("Permission denied"));
 render(<InventoryOperations user={user}/>);
 await screen.findByRole("alert");expect(screen.queryByText(/Posted operation/)).not.toBeInTheDocument();
});

test("operations navigation honors deployment gate",async()=>{
 window.location.hash="#/operations"; api.me.mockResolvedValue({user:{...user,username:"operator",manual_inventory_enabled:true}});
 render(<App/>); await screen.findByRole("heading",{name:"Inventory Operations"});
 expect(screen.getByRole("link",{name:/Inventory Operations/})).toBeInTheDocument();
});
