import React from "react";
import {beforeEach,expect,test,vi} from "vitest";
import {fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {CatalogSpecifications,specificationEntries,RegistrationReview} from "./RegistrationPresentation";
import {AssetRegistrationModal} from "./AssetRegistrationModal";
import {api,request} from "./api";
vi.mock("./api",async importOriginal=>{const original=await importOriginal();return {...original,api:{save:vi.fn()},request:vi.fn()}});
const user={manual_inventory_enabled:true,permissions:["transactions.receive_stock","inventory.add_asset","inventory.view_asset","inventory.view_productmodel","inventory.view_assetcategory","inventory.view_manufacturer","warehouse.view_warehouse","warehouse.view_storagelocation"]};
const model={id:1,name:"Enterprise disk",sku_code:"DISK-01",category:2,category_name:"Storage",manufacturer:3,manufacturer_name:"Example manufacturer",is_active:true,tracking_mode:"SERIALIZED",model_number:"CN8037M676",part_number:"CN8037M676",specifications:{interfaces:{primary:"SAS",optional:null},ports:0,hot_swap:false}};
beforeEach(()=>{
 vi.resetAllMocks();
 request.mockImplementation(async url=>({results:url.includes("product-models")?[model]:url.includes("/warehouses")?[{id:4,name:"North warehouse",is_active:true}]:url.includes("/locations")?[{id:5,name:"Receiving rack",code:"REC",warehouse_id:4,is_active:true},{id:6,name:"Other location",warehouse_id:99,is_active:true}]:url.includes("/categories")?[{id:2,name:"Storage"}]:url.includes("/manufacturers")?[{id:3,name:"Example manufacturer"}]:[],next:null}));
 api.save.mockResolvedValue({operation_key:"never-display-this-operation",assets:[{id:9,asset_tag:"AST-NEW"}],asset_ids:[9],movement_ids:[7],receipt:[{id:7,public_id:"receipt-public",recorded_at:"2026-11-18",operation_type:"STOCK_IN"}],warnings:[]});
});
async function modal(){
 const close=vi.fn();render(<AssetRegistrationModal user={user} onClose={close}/>);
 const dialog=screen.getByRole("dialog",{name:"Register asset"});await within(dialog).findByRole("option",{name:/DISK-01/});
 return {dialog,close};
}
function change(dialog,label,value){fireEvent.change(within(dialog).getByLabelText(label),{target:{value}});}
function fill(dialog){
 for(const [label,value] of [["Product model","1"],["Device name","Server disk"],["Serial number (optional)","00123"],["Destination warehouse","4"],["Destination location","5"],["Condition","USED"],["Stock state","AVAILABLE"],["Description (optional)","Receiving inspection complete"],["Reason / remarks","New equipment received"],["External reference (optional)","DEL-018"]])change(dialog,label,value);
}
test("specifications are labeled, nested and lossless instead of raw JSON",()=>{
 render(<CatalogSpecifications product={model}/>);
 const card=screen.getByRole("region",{name:"Catalog specifications"});
 expect(within(card).getByText("Model number")).toBeInTheDocument();expect(within(card).getByText("Part number")).toBeInTheDocument();
 expect(within(card).getAllByText("CN8037M676")).toHaveLength(2);
 expect(within(card).getByText("Interfaces / Primary")).toBeInTheDocument();expect(within(card).getByText("SAS")).toBeInTheDocument();
 expect(within(card).getByText("0")).toBeInTheDocument();expect(within(card).getByText("No")).toBeInTheDocument();
 expect(card.textContent).not.toContain('{"');expect(model.specifications.interfaces.optional).toBeNull();
});
test("empty and additional catalog specifications remain understandable",()=>{
 const {rerender}=render(<CatalogSpecifications product={{name:"Empty",model_number:"",part_number:null}}/>);
 expect(screen.getByText(/No catalog specifications/)).toBeInTheDocument();
 rerender(<CatalogSpecifications product={{name:"Extra",additional_specifications:{modes:["SR","LR"],firmware:"Unknown"}}}/>);
 expect(screen.getByText("Modes / 1")).toBeInTheDocument();expect(screen.getByText("SR")).toBeInTheDocument();expect(screen.getByText("Unknown")).toBeInTheDocument();
 expect(specificationEntries({model_number:"000123"})[0][1]).toBe("000123");
});
test("modal has one title, five sections, marked required fields and no nested review panel",async()=>{
 const {dialog}=await modal();
 expect(within(dialog).getAllByRole("heading",{level:2})).toHaveLength(1);
 for(const section of ["Product information","Equipment details","Warehouse and location","Condition and stock state","Description and remarks"])expect(within(dialog).getByRole("group",{name:section})).toBeInTheDocument();
 expect(within(dialog).getByLabelText("Device name")).toBeRequired();expect(within(dialog).getByLabelText("Device name").closest(".editor-field")).toHaveClass("is-required");
 expect(within(dialog).getByLabelText("Description (optional)")).toHaveAttribute("rows","2");expect(dialog.querySelector("pre")).toBeNull();
});
test("review is human-readable, complete and does not submit or expose UUIDs",async()=>{
 vi.spyOn(crypto,"randomUUID").mockReturnValueOnce("private-operation-key");
 const {dialog}=await modal();fill(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));
 const review=within(dialog).getByRole("region",{name:"Review registration"});
 for(const text of ["Server disk","Storage","Example manufacturer","Enterprise disk","00123","North warehouse","Receiving rack","Used","Available","New equipment received","DEL-018","Initial stock receipt","Receiving inspection complete"])expect(within(review).getByText(text)).toBeInTheDocument();
 expect(within(review).getByText(/immutable receipt/)).toBeInTheDocument();expect(within(review).getByText(/Generated by the server/)).toBeInTheDocument();
 expect(api.save).not.toHaveBeenCalled();expect(dialog.textContent).not.toContain("private-operation-key");expect(dialog.textContent).not.toContain("operation_key");
 expect(dialog.querySelector("pre")).toBeNull();expect(within(dialog).getByRole("button",{name:"Back to edit"})).toBeInTheDocument();
 crypto.randomUUID.mockRestore();
});
test("Back to edit preserves inputs and the final API contract remains unchanged",async()=>{
 const {dialog}=await modal();fill(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));
 fireEvent.click(within(dialog).getByRole("button",{name:"Back to edit"}));expect(within(dialog).getByLabelText("Device name")).toHaveValue("Server disk");expect(api.save).not.toHaveBeenCalled();
 change(dialog,"Device name","Corrected disk");fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 await within(dialog).findByText("Asset registered");
 const [path,method,body]=api.save.mock.calls[0];expect(path).toBe("/api/transactions/manual/register/");expect(method).toBe("POST");
 expect(body).toEqual({operation_key:expect.any(String),product_model_id:1,destination_location_id:5,device_name:"Corrected disk",serial_raw:"00123",description:"Receiving inspection complete",condition:"USED",state:"AVAILABLE",reason:"New equipment received",external_reference:"DEL-018"});
 expect(dialog.textContent).not.toContain("never-display-this-operation");
 expect(within(dialog).getByText("AST-NEW")).toBeInTheDocument();expect(within(dialog).getByRole("button",{name:"Back to Assets"})).toBeInTheDocument();
});
test("required fields prevent entry into review and location choices follow the warehouse",async()=>{
 const {dialog}=await modal();fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));
 expect(api.save).not.toHaveBeenCalled();expect(within(dialog).queryByRole("heading",{name:"Review asset registration"})).not.toBeInTheDocument();
 change(dialog,"Destination warehouse","4");expect(within(dialog).getByRole("option",{name:"Receiving rack (REC)"})).toBeInTheDocument();expect(within(dialog).queryByRole("option",{name:/Other location/})).not.toBeInTheDocument();
});
test("posting errors show human field labels and preserve corrections",async()=>{
 api.save.mockRejectedValueOnce({status:400,message:"Check the highlighted fields",details:{serial_raw:["Check this serial number"]}});
 const {dialog}=await modal();fill(dialog);fireEvent.click(within(dialog).getByRole("button",{name:"Review registration"}));fireEvent.click(within(dialog).getByRole("button",{name:"Confirm & register"}));
 await within(dialog).findByText("Serial number: Check this serial number");expect(within(dialog).getByLabelText("Serial number (optional)")).toHaveAttribute("aria-invalid","true");expect(within(dialog).getByLabelText("Device name")).toHaveValue("Server disk");
});
test("compact viewport keeps footer actions, dialog semantics and the same route",async()=>{
 const width=window.innerWidth;Object.defineProperty(window,"innerWidth",{configurable:true,value:375});
 const {dialog,close}=await modal();expect(dialog).toHaveAttribute("aria-modal","true");
 expect(dialog.querySelector(".asset-registration-body")).toBeInTheDocument();expect(dialog.querySelector(".asset-registration-footer")).toContainElement(within(dialog).getByRole("button",{name:"Review registration"}));
 fireEvent.click(within(dialog).getByRole("button",{name:"Cancel"}));expect(close).toHaveBeenCalledOnce();Object.defineProperty(window,"innerWidth",{configurable:true,value:width});
});
