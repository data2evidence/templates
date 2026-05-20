### Merge Checklist

Please review this list and check any items that require additions or modifications beyond your core changes. Reviewers can also use it to help confirm that nothing was missed.

- [ ] Import the flow as a .json file and successfully run the flow
- [ ] Switch `DATAFLOW_TEMPLATE_BRANCH` environment variable in docker-compose.yaml to the branch being reviewed and successfully run the flow
- [ ] Each node has a short description that helps the user understand what the node does
- [ ] Added documentation and type hints for embedded Python functions in flow templates (code in the Python node)
- [ ] Result and error are removed in node data i.e. when template is imported there should be no result or error for the nodes
- [ ] Added a description for the flow template, including the OMOP CDM version and supported database(s)