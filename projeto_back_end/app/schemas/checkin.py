from datetime import datetime
from typing import Optional, Dict, Any, List    
from pydantic import BaseModel, Field, field_validator

class CheckInQuestionnaireData(BaseModel):
    """Dados do questionário priódico - preenchido pelo cliente no check-in"""
    appetite: Optional[str] = None # normal | aumentado | diminuído
    intestinal_transit: Optional[str] = Field(default=None, max_length=500) 
    plan_adherence_pct: Optional[int] = Field(default=None, ge=0, le=100)
    training_performance: Optional[int] = Field(default=None, ge=0, le=5)
    recovery_quality: Optional[int] = Field(default=None, ge=1, le=5)
    energy_level: Optional[int] = Field(default=None, ge=1, le=5)
    body_response: Optional[str] = Field(default=None, max_length=500)
    weeks_on_plan: Optional[int] = Field(default=None, ge=0)
    daily_water_intake_l: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    stress_level: Optional[int] = Field(default=None, ge=1, le=5)
    injuries: Optional[str] = Field(default=None, max_length=500)

    @field_validator('appetite')
    @classmethod
    def validate_appetite(cls, value):
        if  value is None:
            return value
        allowed_values = {"normal", "increase", "decrease"}
        if value.lower() not in allowed_values:
            raise ValueError(f"Appetite must be one of the following: {', '.join(allowed_values)}")
        return value.lower()
    
class CheckInPhotoData(BaseModel):
    photo_type: str  # front, side, back
    url: str = Field(min_length=1, max_length=500)         # URL ou caminho para a imagem

    @field_validator('photo_type')
    @classmethod
    def validate_photo_type(cls, value):
        allowed_types = {"front", "side", "back"}
        if value.lower() not in allowed_types:
            raise ValueError(f"Photo type must be one of the following: {', '.join(allowed_types)}")
        return value.lower()
    
#--Trainer cria o pedido --
class CheckInCreate(BaseModel):
    client_id: str
    
#--Cliente responde ao check-in --
class CheckInResponse(BaseModel):
    weight_kg: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    questionnaire: Optional[CheckInQuestionnaireData] = None
    client_notes: Optional[str] = Field(default=None, max_length=500)
    photos: Optional[List[CheckInPhotoData]] = None

#-- Trainer adiciona notas --
class CheckInTrainerNotes(BaseModel):
    trainer_notes: Optional[str] = Field(default=None, max_length=500)

#--Leitura--

class CheckInRead(BaseModel):
    id: str
    client_id: str
    requested_by_trainer_id: str
    status: str
    weight_kg: Optional[float]
    body_fat: Optional[float]
    questionnaire: Optional[Dict[str, Any]]
    client_notes: Optional[str]
    trainer_notes: Optional[str]
    photos: Optional[Dict[str, str]]
    requested_at:datetime
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
 