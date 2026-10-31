# Samples

Small, runnable prototypes and playgrounds for AWS services, grouped the same way as the
site: `samples/<service-id>/<language>/<short-name>/`. The service id matches
`config/services.yaml` (`s3`, `lambda`, `bedrock`, ...), and each service page on the site
links to the samples under its id.

Rules for every sample:

- **One idea per sample.** Show the new feature or API with the least code that runs.
- **README first.** Copy [`_template/README.md`](_template/README.md): what it shows, the
  launch or API change it relates to, how to run it, what AWS resources it creates, what it
  costs, and how to clean up.
- **Nothing secret.** Credentials come from the normal AWS credential chain; configuration
  from environment variables with documented defaults.
- **Self-contained.** Python samples are single files runnable with `uv run` (inline
  `# /// script` dependencies). Node samples carry their own `package.json`.
- **Say if it was run.** The README records the date it last ran successfully, or says it has
  not been run.

| Service | Language | Sample | Shows |
| --- | --- | --- | --- |
| bedrock | python | [converse-stream](bedrock/python/converse-stream/) | Converse streaming API with a Claude model, token usage and latency |
