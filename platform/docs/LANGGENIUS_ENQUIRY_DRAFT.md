# Licence enquiry to LangGenius (Dify): draft

Status: **draft, not sent.** You decide whether and when to send it, and from which address.
Send it through the commercial-licence contact on dify.ai. Nothing below has been sent.

---

**Subject:** Commercial licence question: multi-tenant platform built partly on Dify

Hello,

I'm building NEXORA AI, an enterprise platform that combines voice agents with AI workflows,
knowledge bases and governance for businesses, starting in Saudi Arabia. I've read the Dify Open
Source License and would like to use Dify in a way that respects it, so I have a few questions.

How we plan to use Dify today:

1. **Dedicated installations:** for enterprise customers, one Dify installation per customer, in
   that customer's own cloud or data centre, with a single workspace. NEXORA's own interface
   talks to it through the Service API. Dify's own console stays unmodified, keeping the Dify
   logo and copyright, and is not re-skinned.
2. **Shared cloud:** our multi-tenant cloud does **not** run the Dify application. It uses
   `graphon` and `dify-plugin-daemon` under their Apache-2.0 licences, plus our own code.

Questions:

1. Is (1) permitted under the current licence, including when we charge the customer for NEXORA?
2. Does a single Dify installation with **several workspaces for one customer** (for example
   development, staging and production) count as a multi-tenant environment under the licence?
3. If we later want to run the Dify application in our shared multi-tenant cloud, what commercial
   licence would you offer, and on what terms?
4. Are `graphon` and `dify-plugin-daemon` covered only by Apache-2.0, with no additional Dify
   conditions, as their repositories state?

Thank you for your time. I'm happy to share more detail about the architecture.

Kind regards,
[Your name]
[Company, role]
[Contact details]
