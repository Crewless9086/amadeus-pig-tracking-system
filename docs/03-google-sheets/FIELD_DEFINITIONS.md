# Field Definitions

## Purpose

Defines shared fields that are used across Google Sheets, backend code, n8n workflows, AI agents, and the web app.

## Status And Ownership Fields

| Field | Meaning | Expected values or notes |
| --- | --- | --- |
| `Pig_ID` | Stable pig identifier. | Primary key for pig records. |
| `Order_ID` | Stable order identifier. | Primary key for order headers. |
| `Order_Line_ID` | Stable order line identifier. | Primary key for order lines. |
| `Litter_ID` | Stable litter identifier. | Links litters to pig records. |
| `Mating_ID` | Stable mating record identifier. | Links mating records to breeding overview. |
| `Status` | General record state. | Use `Slaughtered` for pig exit/completed slaughter status. |
| `On_Farm` | Whether a pig is still on farm. | Usually `Yes` or `No`. |
| `Purpose` | Farm purpose for the pig. | Examples include `Unknown`, `Grow_Out`, `Sale`, `Breeding`. `Unknown` must not mean available for sale. |
| `Available_For_Sale` | Final sale availability flag. | `Yes` means visible to sales/order matching; `No` means not sellable. |
| `Is_Sale_Ready` | Formula-derived readiness before final availability gate. | Used by sales formulas. |
| `Reserved_Status` | Whether a pig is available or reserved. | Used by `PIG_OVERVIEW` and sales availability logic. |
| `Reserved_For_Order_ID` | Order currently reserving the pig. | Should be backend-controlled. |

## Order Fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `Order_Status` | Header-level order lifecycle state. | Backend-controlled. |
| `Line_Status` | Order line lifecycle or reservation state. | Backend-controlled. |
| `Requested_Category` | Customer-requested sale category. | Must map to approved sales categories. |
| `Requested_Weight_Range` | Customer-requested weight range or band. | Must map to sheet pricing/availability. |
| `Requested_Quantity` | Quantity requested by customer. | Backend validates availability before reservation. |

## Sales Category Fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `Calculated_Stage` | Formula-derived animal stage. | May use singular labels such as `Young Piglet` internally. |
| `Sale_Category` | Customer-facing category. | Examples: `Young Piglets`, `Weaner Piglets`, `Grower Pigs`, `Finisher Pigs`, `Ready for Slaughter`. |
| `Weight_Band` | Detailed weight bucket. | Examples: `2_to_4_Kg`, `10_to_14_Kg`. |
| `Suggested_Price_Category` | Join key for pricing. | Connects sale category and weight band/range to `SALES_PRICING`. |
| `Category_Code` | Short code for sales category. | Use `RFS` for Ready for Slaughter. |

## Medical Fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `Treatment_Type` | Type of medical treatment. | Current sheet docs include `Vaccination`, `Deworming`, `Antibiotic`, `Iron`, `Vitamin`, `Injury_Treatment`, `Supportive_Care`, `Antiparasitic`, `Other`. |
| `Withdrawal_Days` | Number of withdrawal days for product. | Usually derived from product register. |
| `Withdrawal_End_Date` | Date withdrawal clears. | Used by sale readiness logic. |
| `Withdrawal_Clear` | Formula-derived sale safety flag. | Must be clear before sale availability. |

## Workflow Fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `decision_mode` | AI/n8n branch decision. | Expected values: `AUTO`, `CLARIFY`, `ESCALATE`. |
| `ai_reply_output` | Preserved AI response text. | Should not be overwritten by weaker composer output. |

## Standardized Values

- Pig exit/completed slaughter status: `Slaughtered`.
- Ready for Slaughter category code: `RFS`.
- Sales display weight field: `Weight_Band`.
