# Payment Rules

Agents must not record payment as confirmed from POP alone, change prices autonomously, approve deposits/final balances, create financial records without approved rails, or promise refunds/cancellations without approved policy.

Every sale-bound receipt uses one owner-authenticated canonical action: enter
the actual amount received, preview the exact current sale/payment evidence,
then confirm that digest-bound preview. A full payment must equal the canonical
amount due. A partial payment preserves the actual lesser amount. Preview
writes nothing; confirmation rechecks locked Supabase state and binds replay to
the preserved digest plus a short-lived server-signed sale/actor token. Both
steps require strict owner-admin authentication. Legacy direct payment updates fail closed. Telegram may
link to review but must not claim recording before canonical readback.
New sales start `Unpaid`; they cannot smuggle receipt state through creation.
A later partial receipt may advance only to a greater cumulative received
amount, and settlement becomes `Paid` only when that total equals amount due.

The owner surface is sale-type neutral. Auction transactions are labelled
`Livestock — Auction`, never Slaughter. Completed sale/auction state and
settlement receipt are separate canonical facts; `Fully reconciled` is true
only when both are true. Application, Telegram links and voice-assisted browser
use the same sale-payment preview/confirmation service and identical readback.
Telegram payment confirmation uses the existing Oom Sakkie protected-action
claim and family-message lifecycle: one provider-confirmed preview card with
Confirm and Cancel callbacks bound to the configured owner, provider card,
canonical sale state and exact payment preview digest. The callback re-previews
current truth before the sole Supabase writer runs. Sequential and concurrent
replay create no second write or owner message.

## Zero-consideration disposition

A completed Livestock sale may be corrected to `Charitable_Giveaway` only
through the strict owner-admin, preview/confirm financial-disposition action.
The action keeps the original order, animal-transfer history, line-price
snapshots and `net_total` as list-value evidence, while setting the separate
`receivable_total` and `received_total` to R0.00 and payment status to
`Not_Applicable`. Any earlier receipt state is retained inside immutable
correction evidence; it is not treated as money received. The correction
creates no refund, receipt, invoice, customer message, reservation, allocation
or animal lifecycle effect. Existing commercial documents remain historical
snapshots and must not be presented as a current amount due.
