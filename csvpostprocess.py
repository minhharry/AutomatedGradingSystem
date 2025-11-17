import pandas as pd
from datetime import datetime
import glob
import os

file_paths = glob.glob(r'inputfiles/flowchartl02pdf/grading_results_*.csv')

os.makedirs('outputfiles/flowchartl02pdf', exist_ok=True)
for file_path in file_paths:
    print("Processing file:", file_path)
    df = pd.read_csv(file_path)
    if (df['status'] == 'success').all():
        print("OK")
    else:
        print("ERROR")
    df2 = pd.DataFrame()
    df2['name'] = df['file_path'].apply(lambda path: path.split('\\')[-2].split('_')[-3])
    df2['ex_4'] = df['ex_4_grade']
    df2['ex_5'] = df['ex_5_grade']
    df2['ex_6'] = df['ex_6_grade']
    df2['ex_7'] = df['ex_7_grade']
    df2['ex_8'] = df['ex_8_grade']
    df2['ex_9'] = df['ex_9_grade']
    df2['score'] = df['total_grade']
    df2['max_score'] = df['max_score']
    df2.to_csv(f'outputfiles/flowchartl02pdf/only_score_results_{file_path.split("\\")[-1]}', index=False)