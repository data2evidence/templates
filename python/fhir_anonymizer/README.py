def exec(myinput):
  """ This tool requires a user defined configuration file so that the user
      can choose to hide certain fields of the dataset.
      One such configuration is provided here, copy and paste the contents 
      below into a .json file and upload it to the JsonConfiguration
      node to test the tool.
      For a more specific anonymization behavior, such as date and value perturbation,
      please refer to the website: 
      https://github.com/microsoft/Tools-for-Health-Data-Anonymization/blob/master/README.md
  """
  return  {
            "fhirVersion": "R4",
            "processingError":"raise",
            "fhirPathRules": [
              {"path": "nodesByType('Extension')", "method": "redact"},
              {"path": "Organization.identifier", "method": "keep"},
              {"path": "nodesByType('Address').country", "method": "keep"},
              {"path": "Resource.id", "method": "cryptoHash"},
              {"path": "nodesByType('Reference').reference", "method": "cryptoHash"},
              {"path": "Group.name", "method": "redact"},
              {"path": "nodesByType('identifier').value", "method": "cryptoHash"},
              {
                  "path": "Observation.valueQuantity.value",
                  "method": "perturb",
                  "span": 0.2,
                  "rangeType": "proportional",
                  "roundTo": 0
              },
              { "path": "nodesByType('date')", "method": "dateShift" }
            ],
            "parameters": {
              "dateShiftKey": "",
              "cryptoHashKey": "",
              "encryptKey": "",
              "enablePartialAgesForRedact": true
            }
          }