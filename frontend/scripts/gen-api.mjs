import {writeFile} from 'node:fs/promises';
const target=new URL('../src/lib/api/schema.ts',import.meta.url);
try{const r=await fetch('http://127.0.0.1:8010/openapi.json',{signal:AbortSignal.timeout(2500)});if(!r.ok)throw new Error(`HTTP ${r.status}`);const schema=await r.json();await writeFile(target,`/** Generated from the local TANTARA API OpenAPI document. */\nexport const openApiSnapshot = ${JSON.stringify(schema,null,2)} as const;\n`);console.log('Updated API schema from http://127.0.0.1:8010/openapi.json');}
catch(error){console.log(`API offline (${error.message}); keeping checked-in OpenAPI snapshot.`)}
