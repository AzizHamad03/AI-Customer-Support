# Demonstration store documents

These are fictional policies for development and demonstration.
They contain no real customer data.

Deactivate earlier overlapping demo policies before using this set.
Keep historical messages and citations.

## Initial uploads

Upload each file in policies/ once:

| File | Document title | Category |
| --- | --- | --- |
| shipping_policy.txt | Demo Store Shipping Policy | Shipping |
| returns_policy.txt | Demo Store Returns Policy | Returns |
| product_catalog.txt | Demo Store Product Catalog | Products |
| support_policy.txt | Demo Store Support Policy | General |

Click **Process document** to extract text, prepare chunks, and generate
embeddings. Confirm the document is Ready and available for chat.
If indexing fails, use the same button to retry.

## Development questions

These are development examples, not the final evaluation dataset.

| Question | Expected result |
| --- | --- |
| How much does shipping cost? | SAR 25 below SAR 200; free at SAR 200 or more |
| How long does Riyadh delivery take? | Estimated 2-4 business days after dispatch |
| What about other cities? | Estimated 3-7 business days after dispatch |
| Can I return a personalized item? | Normally no; defective/damaged exception requires review |
| How many days will my refund take? | Exact time unspecified; offer human support |
| My delivery arrived damaged. | 48-hour reporting policy and human-support instructions |
| Where is order DEMO-123? | Cannot verify live status; offer human support |
| Does the Lumi lamp support dimming? | No |
| What are your support opening hours? | Unspecified; do not invent |

## Replacement test

Do not upload shipping_policy_v2.txt as another independent active policy.

1. Ask the shipping-cost question with version 1 active.
2. Open that shipping document and choose Upload replacement.
3. Select replacements/shipping_policy_v2.txt.
4. Before indexing, check that version 1 remains available.
5. Click **Process document** to extract text, prepare chunks, and generate
   embeddings. Confirm the document is Ready and available for chat.
   If indexing fails, use the same button to retry.
6. Check version 2 is active and version 1 is inactive.
7. Ask again: expect SAR 20 below SAR 250, free at SAR 250 or more.
8. Check the earlier answer still retains its original citation.

Freeze the chosen active version before final evaluation.