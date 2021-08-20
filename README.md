# Deploy Cognite Function action
This action deploys a Python function to Cognite Functions, optionally with schedule(s).

## Inputs
### Function metadata in Github Workflow
#### Required
1. `function_name`: Name of your function AND what we will use as `external_id` for the function (plus a small suffix like `-master`). If it is not unique within your project, *the existing function will be overwritten*!
2. `function_folder`: Parent folder of for the function's code.
3. `cdf_deployment_credentials`: The API-key that will be used to deploy the function. It must have the following CDF capabilities: `Files:READ`, `Files:WRITE`, `Functions:READ`, `Functions:WRITE`. You can scope the files-access to a dataset (see 'data_set_external_id')`).
4. `cdf_runtime_credentials`: The API-key that the function will use when running "inside" of Cognite Functions. It must have the CDF capabilities required to run your code.
Example: if your code has to read assets, and write to timeseries, it will need `Assets:READ` and `TimeSeries:WRITE`.

#### Optional
1. `common_folder`:  The path to the folder containing code that is shared between all functions. Defaults to `common/`. More information below.
1. `cdf_project`: The name of your CDF project/tenant. Will be inferred from your API-keys and used to validate against, if given.
2. `cdf_base_url`: Base url of your CDF tenant, defaults to `https://api.cognitedata.com`.
3. `function_file`: The name of the file with your main function (defaults to `handler.py`)
4. `function_secrets`: The name of a Github secret that holds the base64 encoded JSON dictionary with secrets. (see secrets section)
5. `schedule_file`: File location inside `function_folder` containing a list of schedules to be attached to your function. Check out the details in the section below. Note: Ignored with warning if pointing to a non-existent file.
6. `remove_only`: Deletes function along with all attached schedules. Deployment logic is skipped.
7. `data_set_external_id`: Data set external ID (for FilesAPI) to use for the function-associated file (zipped code folder). Note: Requires capability 'dataset:READ' for your `cdf_deployment_credentials` and 'files:WRITE' scoped to either that dataset or 'all'. If your data set is WRITE PROTECTED, you also need to add capability 'dataset:OWNER'. Read more about data sets in the official documentation: [Data sets](https://docs.cognite.com/cdf/data_governance/concepts/datasets/)
8. `cpu`: Set fractional number of CPU cores per function. See defaults and allowed values in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions).
9. `memory`: Set memory per function measured in GB. See defaults and allowed values in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions).
10. `owner`: Used to specify a function's owner. See allowed number of characters in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions)
11. `remove_schedules`: Removes all the schedules linked to a function. 

### Schedule file format
```yaml
- name: Daily schedule
  cron: "0 0 * * *"
  data:
    lovely-parameter: True
    something-else: 42
- name: Hourly schedule
  cron: "0 * * * *"
  data:
    lovely-parameter: False
    something-else: 777
- name: Hourly schedule  # Same name as another schedule (allowed), but with no `data` (also allowed).
  cron: "0 * * * *"
```

### Example usage
Workflow to handle incoming Pull Requests:
See our repository [`deploy-templates`](https://github.com/cognitedata/deploy-functions) for the latest CI/CD workflow examples.

### Common folder
A common use case is that you do not want to replicate utility code between all function folders. In order to accommodate this, we copy all the contents in the folder specified by `common_folder` into the functions we upload to Cognite Functions. If this is not specified, we check if `common/` exists in the root folder and if so, _we use it_.

#### When using a common/shared folder, make sure you don't get a name conflict in one of your functions!

#### Handling imports
A typical setup looks like this:
```
├── common
│   └── utils.py
└── my_function
    └── handler.py
```
The code we zip and send off to the FilesAPI will look like this:
```
├── common
│   └── utils.py
└── handler.py
```
This means your `handler.py`-file should do imports from `common/utils.py` like this:
```py
from common.utils import my_helper1, my_helper2
import common.utils as utils  # alternative
```

### Function secrets
When you implement your Cognite Function, you may need to have additional `secrets`, for example if you want to to talk to 3rd party services like Slack.
To achieve this, you could create the following dictionary:
```json
{"slack-token": "123-my-secret-api-key"}
```
Use your terminal to encode your credentials into a string:
```shell script
$ echo '{"slack-token": "123-my-secret-api-key"}' | base64
eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo=
```
...or use Python if you don't have `base64` available on your system:
```sh
$ echo '{"slack-token": "123-my-secret-api-key"}' | python -m base64
eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo=
```
To decode and verify it, do:
```sh
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | base64 --decode
$ (Alternative using Python:)
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | python -m base64 -d
{"slack-token": "123-my-secret-api-key"}
```
Take that encoded string and store it as a GitHub secret. This secret can now be used by referencing the name (case insensitive) of the secret in your workflow-file. Example:
```yaml
  function_secrets: ${{ secrets.my_secret_name }}
```

Notes: _Keys must be lowercase characters, numbers or dashes (-) and at most 15 characters. You can supply at most 5 secrets in the dictionary (Cognite Functions requirement)_
