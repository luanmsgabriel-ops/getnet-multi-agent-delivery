"""Propostas não confiáveis: sem ferramentas, respostas livres ou identidade de acesso."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class Strict(BaseModel): model_config=ConfigDict(extra='forbid')
class Device(Strict):
    ref:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    label:str=Field(min_length=1,max_length=80)
    store:str=Field(max_length=80)
    quote:str=Field(min_length=1,max_length=800)
class Observation(Strict):
    subject:Literal['device','card','pix']='device'
    scope:Literal['entity','conversation']='entity'
    entity:str|None
    incident:str=Field(max_length=40,description='Stable incident reference, new for a distinct episode. Empty for property.')
    field:Literal['product','country','connection','symptom','error_code','network_ok','restart_attempted','network_menu_open','credential_correct','network_selected','password_entered_on_device','connected','resolved','printing_ok','payment_status','attempt','modality','date']
    value:str=Field(max_length=120)
    status:Literal['asserted','false','unknown','uncertain','corrected','retracted']
    origin:Literal['customer','hypothesis','quoted','third_party']
    retracts:str|None=Field(default=None,max_length=80,description='Only for retracted: assertion_id from prior facts or turn:<zero-based observation index>. Null if unknown. Never target another entity/incident/field.')
    quote:str=Field(min_length=1,max_length=800)
class Request(Strict):
    action:Literal['configure_device','cancel_registration','transfer_funds','contract_service','other']='other'
    subject:Literal['device','card','pix']='device'
    kind:Literal['information','diagnosis','next_step','summary','pause','unsupported_action','clarify','outside','exchange_ambiguous','exchange_reference','exchange_sale']
    topic:Literal['connectivity','decline','comparison','advance','settlement','pix_account','link','link_fee','commercial','migration','installments','global','other']
    entities:list[str]=Field(max_length=6)
    quote:str=Field(min_length=1,max_length=800)
class Turn(Strict):
    devices:list[Device]=Field(max_length=8)
    observations:list[Observation]=Field(max_length=24)
    requests:list[Request]=Field(min_length=1,max_length=8)
    focus:list[str]=Field(max_length=6)
    resolve_pending:list[str]=Field(max_length=8,description='Pending IDs explicitly resolved by this turn; supply a new observation with new evidence.')
