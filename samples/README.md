# Sample and test data

Everything in this folder is **synthetic**. It exists so the dashboard can be
developed and tested without spending API credits, and without using a real
person's resume.

## `sample-resume-jordan-kim.pdf`

A fictional resume used to exercise the upload flow end to end. Jordan Kim does
not exist. The employers named in it are real companies, but the roles,
dates and accomplishments are invented.

Use it to try the Upload a resume button without uploading your own resume.

## `test-fixtures/`

Deliberately awkward inputs used to test the file reader:

| File | What it tests |
| --- | --- |
| `alex-morgan.docx` | Word extraction, including tabs, line breaks and XML entities |
| `broken.docx` | A `.docx` with no `word/document.xml`, which must produce a clear error |
| `plain-resume.txt` | The plain-text path |
| `tiny.txt` | A file too short to be a resume, which must be rejected |

## `cases/*.json`

Five complete mock API responses, one per candidate scenario. They let you test
the entire rendering path with **no API key**: load one, and the board reacts
exactly as it would to a real Claude response.

| File | Scenario it covers |
| --- | --- |
| `austin-finance-data.json` | Metro outside Utah, candidate not relocating |
| `nyc-ml-msc.json` | Masters student, machine learning focus |
| `remote-first-nomad.json` | No home metro at all, remote-only search |
| `toronto-international.json` | Outside the US, would need visa sponsorship |
| `boise-wants-slc.json` | Candidate relocating **to** Salt Lake, so the board stays in local mode |

> **These are fabricated fixtures, not career advice.** The suggested employers
> in them are real companies, but the hiring programs, application windows and
> job titles were written to look plausible for testing. Do not rely on any
> claim in these files. Only a real run against the Claude API produces output
> intended to be acted on, and even then the suggested employers are explicitly
> marked unverified.

### Replaying a case

Serve the folder, open the page, and run this in the browser console:

```js
const data = await (await fetch('/samples/cases/austin-finance-data.json')).json();
const T = window.JobFinderTailor;
const profile = T.buildProfile(data, {
  model: 'claude-opus-5', effort: 'high',
  usage: { input_tokens: 3000, output_tokens: 20000 }, servedBy: 'claude-opus-5',
});
T.applyProfile(profile);          // T.applyProfile(null) restores the built-in board
```
