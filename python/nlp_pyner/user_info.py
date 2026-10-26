class UserInfo(BaseModel):
    """Schema for extracting user information."""
    Medication: List[str] = Field(description="Names of medications mentioned.")
    Condition: List[str] = Field(description="Medical conditions, diagnoses, or symptoms.")
    SubstanceUse: List[str] = Field(description="Substances used, such as alcohol or tobacco.")
    Procedure: List[str] = Field(description="Medical procedures or interventions.")
    Formulation: List[str] = Field(description="Medication formulations, e.g., powder, solution, injection.")
    Frequency: List[str] = Field(description="Frequency of medication administration, e.g., BID, TID.")
    Dosage: List[str] = Field(description="Dosages of medications, e.g., 500 mg, 5,000 unit/mL.")
    Route: List[str] = Field(description="Routes of medication administration, e.g., oral, topical, injection.")
    Duration: List[str] = Field(description="Duration of medication use or treatment.")

def exec(myinput):
    return UserInfo