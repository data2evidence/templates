### Merge Checklist

Please review this list and check any items that require additions or modifications beyond your core changes. Reviewers can also use it to help confirm that nothing was missed.


### Test if the flow runs successfully as an imported json file
- [ ] Import the flow as a .json file and successfully run the flow

### Test if the flow runs successfully as template
- [ ] Switch `DATAFLOW_TEMPLATE_BRANCH` environment variable in docker-compose.yaml to the branch being reviewed and successfully run the flow

### Inspect the nodes in the flow (either as a template or imported json file):
- [ ] Each node has a short description that helps the user understand what the node does
- [ ] Added documentation and type hints for embedded Python functions in flow templates (code in the Python node)
- [ ] Result and error are removed in node data i.e. there should be no result or error visible for the nodes

### [Currently not visible in UI]
- [ ] Added a description for the flow template, including the OMOP CDM version and supported database(s)