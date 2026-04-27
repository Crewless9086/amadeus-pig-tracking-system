# Media Tool Workflow

## n8n Workflow Name

`1.3 - SAM - Sales Agent - Media Tool`

## Purpose

Media operation workflow called by the sales workflow for specific media related tasks. This workflows is used to do all the media. If clients ask for products pictures they get the pictures related to that product. This is still in the developing fase and can be set up to work best with this program. 

The current idea is this workflow will process images requested. This workflow will be connected to 
"1.0 - SAM - Sale Agent - Chatwoot" who will only be able to send the clients on request images of the products required.  

## Export File

Place the current n8n export in `workflow.json` when available.


## Trigger / Called By
When Executed by Another Workflow

## Inputs
Input data mode
Define using fields below
Workflow Input Schema

Values 1
Name
account_id
Type
Number

Values 2
Name
conversation_id
Type
Number

Values 3
Name
inbox_id
Type
Number

Values 4
Name
category_key
Type
String

Values 5
Name
send_mode
Type
String

Values 6
Name
count
Type
Number


## Outputs
[
  {
    "account_id": null,
    "conversation_id": null,
    "inbox_id": null,
    "category_key": null,
    "send_mode": null,
    "count": null
  }
]

## Main Flow
1. When Executed by Another Workflow
2. Resolve Config + Defaults
const body = $json;

const MEDIA_CONFIG = {
  newborns: { folder_id: "1wSMHb1QiEiEvUkdfH7S8jyoh43_c7krI", display: "Newborn piglets" },
  weaners:   { folder_id: "1FBLSZmd_h8VTGPIHYSFLx0UvgSMGQpsg", display: "Weaner piglets" },
  growers:   { folder_id: "1S6HqMrLD9rnrzX6nnCWXt4On9sjseok2", display: "Grower pigs" },
  finishers: { folder_id: "1zzW5I1iDflXyG2OUFUoiIcpWysJ8RNw3", display: "Finisher pigs" },
  slaughter: { folder_id: "1aVzYeQlRJu0bbLcMhO2G3zAuNXQV94Wu", display: "Slaughter pigs" }
};

const category = (body.category_key || "").toLowerCase().trim();
if (!MEDIA_CONFIG[category]) {
  return [{
    error: `Unknown category_key: ${category}`,
    ok: false
  }];
}

return [{
  ok: true,
  account_id: Number(body.account_id || 147387),
  conversation_id: Number(body.conversation_id),
  inbox_id: Number(body.inbox_id || 0),
  category_key: category,
  folder_id: MEDIA_CONFIG[category].folder_id,
  category_display: MEDIA_CONFIG[category].display,
  send_mode: (body.send_mode || "latest").toLowerCase(),
  count: Number(body.count || 5)
}];

3. Get Conversation
Method
GET
URL
https://app.chatwoot.com/api/v1/accounts/{{$json.account_id}}/conversations/{{$json.conversation_id}}
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: TRUE
Specify Headers
Using Fields Below
Headers

api_access_token
Name
api_access_token
Value
F5tQGAj9v4KCrV7cio8SGhEe

Send Body: FALSE

4. Read Offset + Decide Slice
const cfg = $items("Resolve Config + Defaults")[0].json;
const convo = $json?.data || $json; // depending on node output shape
const attrs = convo?.custom_attributes || convo?.conversation?.custom_attributes || {};

let offsetMap = {};
try {
  offsetMap = JSON.parse(attrs.images_sent_offset_map || "{}");
} catch (e) {
  offsetMap = {};
}

const category = cfg.category_key;
const currentOffset = Number(offsetMap[category] || 0);
const sendMode = cfg.send_mode;
const count = cfg.count;

const offset = (sendMode === "next") ? currentOffset : 0;

return [{
  ...cfg,
  current_offset: currentOffset,
  offset,
  offset_map: offsetMap
}];

5. List Files
Credential
Google Drive account
Resource
File/Folder
Operation
Search
Search Method
Advanced Search
Query String
'{{ $json.folder_id }}' in parents and trashed=false and mimeType contains 'image/'
 
'1wSMHb1QiEiEvUkdfH7S8jyoh43_c7krI' in parents and trashed=false and mimeType contains 'image/'

Return All: TRUE

6. Sort + Select 5
const meta = $items("Read Offset + Decide Slice")[0].json;
const files = $json?.files || $json; // depending on node output

// Normalize array
const arr = Array.isArray(files) ? files : (files.files || []);

// Filter images only
const images = arr.filter(f => (f.mimeType || "").startsWith("image/"));

// Sort newest first by createdTime (fallback modifiedTime)
images.sort((a, b) => {
  const ta = new Date(a.createdTime || a.modifiedTime || 0).getTime();
  const tb = new Date(b.createdTime || b.modifiedTime || 0).getTime();
  return tb - ta;
});

const offset = meta.offset;
const count = meta.count;
const selected = images.slice(offset, offset + count);

return [{
  ...meta,
  total_images_in_folder: images.length,
  selected_count: selected.length,
  selected_files: selected.map(f => ({
    id: f.id,
    name: f.name,
    mimeType: f.mimeType,
    createdTime: f.createdTime,
    webViewLink: f.webViewLink,
  }))
}];

7. Any files selected?
Conditions
{{$json.selected_count}}
 

is greater than
0

Only TRUE path is connected

8.1.1 Update Offset Map
const meta = $items("Sort + Select 5")[0].json;
const category = meta.category_key;

const newMap = meta.offset_map || {};
const newOffset = meta.offset + meta.selected_count;
newMap[category] = newOffset;

return [{
  account_id: meta.account_id,
  conversation_id: meta.conversation_id,
  category_key: category,
  sent_count: meta.selected_count,
  new_offset: newOffset,
  images_sent_offset_map: JSON.stringify(newMap),
  now_iso: new Date().toISOString()
}];

8.1.2 Patch Conversation Attributes
Method
PATCH
URL
https://app.chatwoot.com/api/v1/accounts/{{$json.account_id}}/conversations/{{$json.conversation_id}}/custom_attributes
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: TRUE
Specify Headers
Using Fields Below
Headers

api_access_token

Content-Type

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{
  "custom_attributes": {
    "last_images_sent_at": "={{$json.now_iso}}",
    "last_images_sent_category": "={{$json.category_key}}",
    "last_images_sent_count": "={{$json.sent_count}}",
    "images_sent_offset_map": "={{$json.images_sent_offset_map}}"
  }
}

8.1.3 Internal Note
Method
POST
URL
https://app.chatwoot.com/api/v1/accounts/{{$json.account_id}}/conversations/{{$json.conversation_id}}/messages
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: FALSE

Send Body: TRUE
Body Content Type
JSON
Specify Body
Using JSON
JSON
{
  "content": "Sent {{$json.sent_count}} images ({{$json.category_key}}). New offset={{$json.new_offset}}.",
  "message_type": "outgoing",
  "private": true
}
 
8.2.1 Explode Files
Mode: Run Once for All Items
const files = $json.selected_files || [];
return files.map(f => ({ ...$items()[0].json, file: f }));

8.2.2 Split Out
Fields To Split Out
{{$json.selected_files}}
Use $binary to split out the input item by binary data
Include
No Other Fields

8.2.3 Download file
Credential
Google Drive account
Resource
File
Operation
Download
File
By ID
{{$json.file.id}}
 
Options
Put Output File in Field
data
The name of the output binary field to put the file in
File Name
{{ $json.name }}

8.2.4 Send Attachment to Chatwoot
Method
POST
URL
https://app.chatwoot.com/api/v1/accounts/{{$json.account_id}}/conversations/{{$json.conversation_id}}/messages
 
Authentication
None

Send Query Parameters: FALSE

Send Headers: TRUE
Specify Headers
Using Fields Below
Headers

api_access_token
Name
api_access_token
Value
F5tQGAj9v4KCrV7cio8SGhEe

Send Body: TRUE
Body Content Type
Form-Data
Body

content
Type
Form Data
Name
content
Value

message_type
Type
Form Data
Name
message_type
Value
outgoing

private
Type
Form Data
Name
private
Value
false

attachments[]
Type
n8n Binary File
Name
attachments[]
Input Data Field Name
data


## Important Rules
What must not be changed.

## Known Issues / Questions
Anything you are unsure about.