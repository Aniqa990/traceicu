import pandas as pd

df = pd.read_csv('evaluation/results.csv')

# Group by issue type
print('=== FAILURE PATTERNS ===')
print()

# 1. Status disconnects - expected supported but got abstain
status_mismatch = df[(df['expected_status'] == 'supported') & (df['got_status'] == 'abstain')]
print(f'1. Should be SUPPORTED but got ABSTAIN: {len(status_mismatch)} cases')
if len(status_mismatch) > 0:
    print('   Reasons:', status_mismatch['reason'].value_counts().to_dict())
    print('   Concepts:', status_mismatch['concept'].value_counts().to_dict())
print()

# 2. Fact accuracy - correct status but wrong answer
fact_fail = df[(df['status_correct'] == True) & (df['fact_accuracy'] == False)]
print(f'2. CORRECT STATUS but WRONG ANSWER: {len(fact_fail)} cases')
if len(fact_fail) > 0:
    print('   Sample issues:')
    for idx, row in fact_fail.head(3).iterrows():
        q = row['question'][:60] if pd.notna(row['question']) else 'N/A'
        a = str(row['answer'])[:100] if pd.notna(row['answer']) else 'N/A'
        print(f"      {row['id']}: {q}...")
        print(f"         Got: {a}...")
print()

# 3. Out of scope handling
out_of_scope = df[df['expected_status'] == 'abstain']
print(f'3. OUT-OF-SCOPE questions: {len(out_of_scope)} cases')
correct_abstain = out_of_scope[out_of_scope['abstain_correct'] == True]
print(f'   Correctly abstained: {len(correct_abstain)} / {len(out_of_scope)}')
print()

# 4. Summary stats
print('=== OVERALL METRICS ===')
print(f'Total questions: {len(df)}')
print(f'Status correct: {df["status_correct"].sum()} / {len(df)}')
print(f'Fact accuracy: {df["fact_accuracy"].sum()} / {len(df)}')
temporal_count = df['temporal_accuracy'].sum()
print(f'Temporal accuracy: {temporal_count} / {len(df)}')

print()
print('=== DETAILED BREAKDOWN ===')
print()
print('Issues by intent:')
intent_fails = df.groupby('intent').apply(lambda x: (x['fact_accuracy'].sum(), len(x)))
for intent, (pass_count, total) in intent_fails.items():
    if pd.notna(intent):
        print(f"  {intent}: {pass_count}/{total}")
