# Demonstration store documents

These are fictional policies for development and demonstration.
They contain no real customer data.

Deactivate earlier overlapping demo policies before using this set.
Keep historical documents, messages, and citations.

## Start the application

From the project root, activate your virtual environment and run:

```bash
source .venv/bin/activate
python manage.py runlocal
```

This starts both the web server and the document-processing worker.
Keep the command running while using the application.

Document processing starts automatically in the background after you click
**Process document**. You do not need to start a separate worker terminal
when using `runlocal`.

Press **Control+C** to stop both processes.

## Initial uploads

In **Staff workspace → Manage documents**, upload each file in `policies/`
once, using these exact titles:

| File | Document title | Category |
| --- | --- | --- |
| `shipping_policy.txt` | Demo Store Shipping Policy | Shipping |
| `returns_policy.txt` | Demo Store Returns Policy | Returns |
| `product_catalog.txt` | Demo Store Product Catalog | Products |
| `support_policy.txt` | Demo Store Support Policy | General |

For each document:

1. Open its detail page.
2. Click **Process document**.
3. The request queues a background job and returns to the page promptly.
4. Wait for the job to finish. The page refreshes automatically while the
   job is queued or processing.
5. Confirm the job shows **Succeeded**, the document is **Ready**, and the
   document is active.

You can leave or refresh the page while processing continues.

The worker extracts text, prepares chunks, and generates embeddings.
A small document may finish before you see the **Processing** state.

Repeated submissions while a job is queued or processing reuse the existing
job. If processing fails, review the displayed error and click
**Retry processing** after resolving the cause.

If a document remains queued, check that `python manage.py runlocal` is
still running and review its terminal output.

## Development questions

These are manual development and demonstration examples. They are separate
from the labeled retrieval datasets in `evaluation/`.

| Question | Expected result |
| --- | --- |
| How much does shipping cost? | SAR 25 below SAR 200; free at SAR 200 or more |
| How long does Riyadh delivery take? | Estimated 2–4 business days after dispatch |
| What about other cities? | After the Riyadh question, estimated 3–7 business days after dispatch |
| Can I return a personalized item? | Normally no; defective or damaged exceptions require review |
| How many days will my refund take? | Exact time unspecified; offer human support |
| My delivery arrived damaged. | 48-hour reporting policy and human-support instructions |
| Where is order DEMO-123? | Cannot verify live status; offer human support |
| Does the Lumi lamp support dimming? | No |
| What are your support opening hours? | Unspecified; do not invent |

The 48-hour reporting period comes from the demonstration policy document.
It should not be hardcoded into the answer prompt.

## Retrieval evaluation setup

The fixed retrieval datasets are:

- `evaluation/retrieval_dev.json`: 8 development cases.
- `evaluation/retrieval_eval.json`: 20 evaluation cases.

The runner requires exactly the four documents listed above to be active,
Ready, and version 1. Their extracted content must match the corresponding
files in `policies/`, and all their chunks must have embeddings.

Deactivate additional demonstration documents before running the evaluation.
Do not delete historical documents or citations.

With `RETRIEVAL_MAX_DISTANCE=0.80`, run the development evaluation first:

```bash
python manage.py evaluate_retrieval --split dev --label threshold_0_8
```

After checking the development results, evaluate the fixed cutoff:

```bash
python manage.py evaluate_retrieval --split eval --label threshold_0_8
```

The commands save timestamped reports in `evaluation/results/`.
The label controls the report filename; the configured setting controls
the actual retrieval cutoff.

Keep the datasets and original baseline reports unchanged when comparing
results. See the root README for the recorded baseline and filtered results.

These commands evaluate retrieval and follow-up rewriting. They do not
measure complete answer quality or ticket workflows.

Once the documents are Ready, the evaluation commands do not require the
web server or document worker to be running.

## Background-processing demonstration

Use a separate small TXT document titled **Background Processing Demo**
to demonstrate background processing without changing the four policy files.

1. Start the application with `python manage.py runlocal`.
2. Upload the demonstration document.
3. Click **Process document**.
4. Leave or refresh the page while the job runs.
5. Reopen the document and confirm the job succeeded and the document is Ready.
6. Deactivate this extra document afterward so it does not affect retrieval
   evaluation.

To observe a persistent **Queued** state, you can temporarily run only
`python manage.py runserver`, submit the document, and then stop that server
and start `python manage.py runlocal`. The worker will pick up the saved job.

## Replacement test

This test changes the active shipping policy to version 2. Complete any
evaluation that requires the four version-1 documents before performing it.
For repeated benchmark work, use a separate demonstration database for the
replacement test.

Do not upload `replacements/shipping_policy_v2.txt` as an independent active
policy.

1. With version 1 active, ask the shipping-cost question. Expect SAR 25 below
   SAR 200 and free shipping at SAR 200 or more.
2. Open the shipping document and choose **Upload replacement**.
3. Select `replacements/shipping_policy_v2.txt`.
4. Confirm version 1 remains active before processing the replacement.
5. Click **Process document** on the replacement.
6. While the replacement is queued or processing, version 1 remains active.
7. Wait for processing to succeed. Confirm version 2 is Ready and active,
   and version 1 is inactive.
8. Ask the shipping-cost question again. Expect SAR 20 below SAR 250 and
   free shipping at SAR 250 or more.
9. Check that the earlier answer still retains its original citation.

If replacement processing fails, version 1 remains active.
Resolve the cause and click **Retry processing** on the replacement.

The switch from the original document to its replacement occurs only after
replacement indexing succeeds.

The existing retrieval evaluation dataset requires version 1. Results
collected with version 2 would use a different corpus and should not be
presented as a direct comparison with the recorded version-1 baseline.