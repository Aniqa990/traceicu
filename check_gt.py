import json

# Load ground truth to see what SHOULD happen
with open('evaluation/ground_truth.json') as f:
    gt_data = json.load(f)

# Find Q001 ground truth
q001 = [x for x in gt_data if x['id'] == 'Q001'][0]
print("Q001 Ground Truth:")
print(json.dumps(q001, indent=2))
print()

# Find what the result says
import pandas as pd
df = pd.read_csv('evaluation/results.csv')
q001_result = df[df['id'] == 'Q001'].iloc[0]
print("Q001 Result:")
print(f"  Status: expected={q001_result['expected_status']}, got={q001_result['got_status']}")
print(f"  Reason: {q001_result['reason']}")
print(f"  Concept: {q001_result['concept']}")
print(f"  Answer: {q001_result['answer']}")
print()

# Check some glucose queries
print("Glucose Issues:")
for qid in ['Q021', 'Q023', 'Q025']:
    q_gt = [x for x in gt_data if x['id'] == qid]
    q_result = df[df['id'] == qid].iloc[0]
    if q_gt:
        print(f"\n{qid}:")
        print(f"  Expected: {q_gt[0].get('expected_answer', 'N/A')}")
        print(f"  Got: {q_result['answer'][:80]}")
        print(f"  GT details: {json.dumps(q_gt[0], indent=4)[:200]}...")
