def exec(myinput):
    azure_config = ModelConfig(
        provider = 'azure',
        model_name = 'gpt-4o',
        azure_deployment = Variable.get('azure_openai_api_deployment_name'),
        azure_endpoint = Variable.get('azure_openai_api_endpoint'),
        azure_api_version = Variable.get('azure_openai_api_version'),
        max_tokens=200,
        top_p=0.8
    )
    return azure_config