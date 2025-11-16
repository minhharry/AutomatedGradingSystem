import pandas as pd
from datetime import datetime

df = pd.read_csv('inputfiles/grading_results_20251107_225808.csv')

df2 = pd.DataFrame()
df2['name'] = df['file_path'].apply(lambda path: path.split('\\')[-2].split('_')[-3])
df2['score'] = df['total_grade']
df2['max_score'] = df['max_score']

df2.to_csv(f'inputfiles/only_score_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv', index=False)