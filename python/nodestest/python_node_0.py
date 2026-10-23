import pandas as pd           
from typing import Any 
                                        
def exec(myinput: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    df = myinput["r_node_0"].result                                                                                                                     
    filtered = df[df["cohort_id"].isin([36, 49])]
    return {                                                                                                                                            
        "cohort_members": filtered.to_dict(orient="records")
    } 