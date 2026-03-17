from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import SQLModel, Field

#---------------------------------------------
#Questionário subschema de validação de tipagem
#---------------------------------------------

class QuestionnaireData(BaseModel):
    """
    Estrutura do questionário de avaliação.

    Todos os campos são opcionais no schema base.
    A obrigatoriedade de 'injuries' na primeira avaliação
    é validada a nível de router, não aqui.
    """

    #apetite: normal | aumentado | diminuído
    appetite: Optional[str] = None

    #Transito intestinal: texto livre ou escala
    intestinal_transit: Optional[str] = Field(default=None, max_length=200)

    #cumprimento dos planos  em percentual
    plan_adherence_pct: Optional[int] = Field(default=None, ge=0, le=100)

    #Rendimento do treino: escala de 1 a 5
    training_performance: Optional[int] = Field(default=None, ge=1, le=5)

    #Recuperação muscular / qualidade do sono: escala de 1 a 5
    recovery_quality: Optional[int] = Field(default=None, ge=1, le=5)

    #Nível de energia durante o dia: escala de 1 a 5
    energy_level: Optional[int] = Field(default=None, ge=1, le=5)

    #Sensação de resposta do corpo: texto livre
    body_response: Optional[str] = Field(default=None, max_length=500)

    #Nº de semanas com esse plano de treino
    weeks_on_plan: Optional[int] = Field(default=None, ge=0)

    #Consumo de água diária em litros
    daily_water_intake_l: Optional[float] = Field(default=None, ge=0, le=20)

    #Nível de stresse percebido: escala de 1 a 5
    stress_level: Optional[int] = Field(default=None, ge=1, le=5)

    #Lesões ou dores: texto livre (obrigatório na primeira avaliação, opcional nas seguintes)
    injuries: Optional[str] = Field(default=None, max_length=500)

    @field_validator('appetite')
    @classmethod
    def validate_appetite(cls, v: Optional[str]) -> Optional[str]:
        #Garante que o apetite seja um dos valores permitidos, se fornecido
        if v is None:
            return v
        allowed = {"normal", "aumentado", "diminuído"}
        if v.lower() not in allowed:
            raise ValueError(f"Apetite deve ser um de: {', '.join(allowed)}")
        return v.lower()
    

    #---------------------------------------------
    #Measurements - Perimetros e composições corporais
    #---------------------------------------------

class MeasurementCreate(BaseModel):
    """
    Payload para um perimetro corporal.
    """

    measurement_type: str = Field(min_length=1, max_length=50)
    value_cm: float = Field(ge=0.0, le=300.0)

class MeasurementRead(BaseModel):
    """
    Schema para leitura de um perimetro corporal.
    usado em respostas de API
    """

    id: int
    measurement_type: str
    value_cm: float


#---------------------------------------------
#Photo - Fotos de progresso
#---------------------------------------------

class PhotoCreate(BaseModel):
    #Payload para adicionar foto á avaliação
    photo_type: str = Field(min_length=1, max_length=50)
    url: str = Field(min_length=1, max_length=500)

    @field_validator('photo_type')
    @classmethod
    def validate_photo_type(cls, v: str) -> str:
        allowed = {"frontal", "lateral", "posterior"}
        if v.lower() not in allowed:
            raise ValueError(f"photo_type deve ser um de: {', '.join(allowed)}")
        return v.lower()
    
class PhotoRead(BaseModel):
    #Schema para leitura de uma foto de avaliação.
    id: int
    photo_type: str
    url: str

#---------------------------------------------
#Assessment - Avaliação física
#---------------------------------------------

class AssessmentCreate(BaseModel):
    """
    Payload para criar uma avaliação física.

    'measurements' e 'photos' são enviadas no mesmo request
    para permitir criação atômica da avaliação com seus dados relacionados.
    """

    client_id: str
    weight_kg: float = Field(ge=0.0, le=500.0)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    notes: Optional[str] = Field(default=None, max_length=500)

    #questionário tipado -serializado como JSON no banco
    questionnaire: Optional[QuestionnaireData] = None

    #perimetos corporais
    measurements: Optional[List[MeasurementCreate]] = Field(default_factory=list)

    #fotos de progresso
    photos: Optional[List[PhotoCreate]] = Field(default_factory=list)

class AssessmentRead(BaseModel):
    """
    Schema para leitura de uma avaliação física.
    Inclui os dados relacionados de questionário, perimetros e fotos.
    """

    id: int
    client_id: str
    weight_kg: float
    body_fat: Optional[float] = None
    notes: Optional[str] = None

    #Questionario devolvido como dict 
    questionnaire: Optional[Dict[str, Any]] 
    measurements: List[MeasurementRead]
    photos: List[PhotoRead]

    archived_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        #permite construir o schema a partit dos objetos ORM
        from_attributes = True


