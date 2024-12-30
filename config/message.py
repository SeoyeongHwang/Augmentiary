DIARY_ANALYSIS_PROMPT = """Read the user's diary and, based on their attitudes and values, 
find things to be positive about or grateful for in the diary. 
Semantically reflect your findings and cover up the diary using the user's preferred language. 
Maintain a first-person perspective. Make it natural and authentic. 

The tone should be '{tone}'. 
Here's an example of writing in this tone:
---
{tone_example}
---

The diary content is as follows:\n\n

Attitude: {attitude},
Value: {value},
Diary: {diary}"""