import gradio as gr
from google import genai 
import os
import glob
import pandas as pd
import time
from datetime import datetime
import json
from dotenv import load_dotenv
load_dotenv()
import os

# Configure Gemini API
def configure_gemini_client(api_key):
    """Configure the Gemini API with the provided key and return a client."""
    return genai.Client(api_key=api_key) 

def scan_folder(folder_path, file_extensions):
    """Scan folder recursively and return list of files matching extensions."""
    files = []
    extensions = [ext.strip() for ext in file_extensions.split(',')]
    
    for ext in extensions:
        if not ext.startswith('.'):
            ext = '.' + ext
        pattern = os.path.join(folder_path, '**', f'*{ext}')
        files.extend(glob.glob(pattern, recursive=True))
    
    return sorted(files)

def upload_to_gemini(client, file_path): 
    """Upload a file to Gemini and return the file object."""
    try:
        # Use client.files.upload
        uploaded_file = client.files.upload(file=file_path) 
        return uploaded_file
    except Exception as e:
        raise Exception(f"Upload failed: {str(e)}")

def grade_file(client, file_path, exercise_problem): 
    """
    Grade a single file using Gemini API.
    Returns a dictionary:
    - On success: {'status': 'success', 'data': [list_of_exercise_results]}
    - On failure: {'status': 'failed', 'error': 'error message'}
    """
    uploaded_file = None
    model_name = 'gemini-2.5-flash' # Using 2.5 Flash
    try:
        # 1. Upload file to Gemini
        uploaded_file = upload_to_gemini(client, file_path) 
        
        # 2. Wait for file to be processed
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            # Use client.files.get
            uploaded_file = client.files.get(name=uploaded_file.name) 
        
        if uploaded_file.state.name == "FAILED":
            raise Exception("File processing failed on Gemini's end")
        
        # 3. Create the grading prompt
        system_prompt = f"""You are a **supportive and encouraging** automated grading assistant. Your primary goal is to find opportunities to **reward student effort and understanding**, not to needlessly penalize minor mistakes or differences in style.

You MUST provide your response as a single, valid JSON array.
Do not include any text before or after the JSON array (e.g., do not write "Here is the JSON...").

The JSON array must contain one object for EACH exercise you find in the "EXERCISE PROBLEM(S)" list.
The student submission is a single file; you must evaluate how it attempts to solve *all* the exercises.

Each object in the array must have the following keys:
- **"exercise_id"**: A string identifier for the exercise (e.g., "1", "2a", "3"). This should match the numbering in the problem list.
- **"is_attempted"**: A boolean (true/false). This is 'true' if the student wrote any code or text that attempts to solve this specific exercise, even if the solution is incomplete or wrong. It is 'false' only if the exercise is completely ignored.
- **"feedback"**: A string containing detailed, constructive feedback but short and concise for this *specific exercise*. Explain what they did well and what they can improve. 
- **"grade"**: A numerical score based on the following scale:
    - **1**: **Correct Concept & Goal Achieved.** The solution is functionally correct or clearly demonstrates a strong, correct grasp of the exercise's main goal. **Prioritize correct core logic over perfect syntax or minor implementation details.** Tiny, insignificant errors or stylistic differences are acceptable.
    - **0.5**: **Partial Understanding or Good Effort.** The student **clearly understood the core concept** or **implemented a significant part of the solution correctly**, even if there are several logic errors, bugs, or missing pieces. **Be generous with this score;** reward valid attempts and partial understanding.
    - **0**: **Significant Error or Not Seen.** The solution is fundamentally wrong (e.g., doesn't address the prompt, shows no logical path to a solution) or it's missing (and "is_attempted" is false).


**IMPORTANT (Benefit of the Doubt):** Students can be very creative and may find novel or non-standard solutions. Examine these solutions carefully. **If a creative approach still correctly solves the exercise, it must receive a 1.** When in doubt, give the student the benefit of the doubt.
---
EXERCISE PROBLEM(S):
{exercise_problem}
---

Now, please evaluate the following student submission file based on ALL the exercises listed above. Provide the JSON array response.
"""
        
        # 4. Generate summary
        response = client.models.generate_content( 
            model=model_name,
            contents=[system_prompt, uploaded_file],
            # Add generation_config to ensure JSON output
            config=genai.types.GenerateContentConfig(
                top_p=0.5,
                temperature=0.5,
                response_mime_type="application/json",
                thinking_config=genai.types.ThinkingConfig(thinking_budget=-1)
            )
        )
        
        # 5. Post-process to extract JSON
        try:
            json_text = response.text.strip()
            data = json.loads(json_text)
            
            if not isinstance(data, list):
                raise json.JSONDecodeError("LLM did not return a JSON list.", json_text, 0)
            
            if not data:
                # Handle case where LLM returns empty list
                 return {
                    'status': 'failed',
                    'error': 'Grader returned an empty result list.'
                }

            # NEW: Return the raw data list on success
            return {
                'status': 'success',
                'data': data
            }
            
        except json.JSONDecodeError as e:
            # LLM failed to return valid JSON
            return {
                'status': 'failed',
                'error': f"Failed to parse LLM response. Raw: {response.text}"
            }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }
    finally:
        # 6. Clean up uploaded file
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name) 
            except Exception as e:
                print(f"Warning: Failed to delete file {uploaded_file.name}. Error: {e}")


def _flatten_results_to_row(result_data, file_result_dict):
    """
    Helper to populate a file_result dict with flattened and aggregated keys
    from the 'data' list returned by grade_file.
    """
    total_score = 0
    max_score = 0
    all_attempted = True
    feedback_parts = []

    if not result_data: # Handle empty data list
        file_result_dict['grade'] = '0 / 0'
        file_result_dict['feedback'] = 'No exercises found or graded.'
        file_result_dict['is_complete'] = False
        file_result_dict['total_grade'] = 0
        file_result_dict['max_score'] = 0
        return

    for ex in result_data:
        exercise_id = ex.get('exercise_id', 'N/A')
        is_attempted = ex.get('is_attempted', False)
        grade = ex.get('grade', 0)
        feedback = ex.get('feedback', 'No feedback.')
        
        # Add to total score
        if isinstance(grade, (int, float)):
            total_score += grade
        max_score += 1 # Each exercise is 1 point max
        
        if not is_attempted:
            all_attempted = False
        
        # Format feedback for UI
        feedback_parts.append(f"**Exercise {exercise_id} (Grade: {grade}):**\n{feedback}\n")
        
        # Add dynamic columns for CSV
        file_result_dict[f"ex_{exercise_id}_grade"] = grade
        file_result_dict[f"ex_{exercise_id}_feedback"] = feedback
        file_result_dict[f"ex_{exercise_id}_attempted"] = is_attempted

    # Add aggregated keys for UI
    file_result_dict['grade'] = f"{total_score} / {max_score}"
    file_result_dict['feedback'] = "\n".join(feedback_parts)
    file_result_dict['is_complete'] = all_attempted
    file_result_dict['total_grade'] = total_score
    file_result_dict['max_score'] = max_score


def _get_csv_columns(dataframe):
    """Helper to get ordered columns for CSV export."""
    all_columns = dataframe.columns
    core_cols = [
        'file_path', 'file_name', 'status', 'grade', 'total_grade', 
        'max_score', 'is_complete', 'error', 'timestamp'
    ]
    # Find all 'ex_...' columns and sort them
    dynamic_cols = sorted([col for col in all_columns if col.startswith('ex_')])
    
    # Ensure we only include core_cols that actually exist
    final_core_cols = [col for col in core_cols if col in all_columns]
    
    return final_core_cols + dynamic_cols


def process_submissions(api_key, folder_path, file_extensions, exercise_problem, progress=gr.Progress()):
    """Process all files in the folder and generate grades."""
    if not api_key:
        return "Please provide a Gemini API key", None, [], None
    
    if not folder_path or not os.path.exists(folder_path):
        return "Please provide a valid folder path for submissions", None, [], None
    
    if not exercise_problem.strip():
        return "Please paste the exercise problem statement(s)", None, [], None
        
    try:
        # Configure Gemini
        client = configure_gemini_client(api_key) 
        
        # Scan for files
        progress(0, desc="Scanning folder...")
        files = scan_folder(folder_path, file_extensions)
        
        if not files:
            return f"No submission files found with extensions: {file_extensions}", None, [], None
        
        # Process each file
        results = []
        
        for idx, file_path in enumerate(files):
            progress((idx / len(files)), desc=f"Grading {idx + 1}/{len(files)}: {os.path.basename(file_path)}")
            
            result = grade_file(client, file_path, exercise_problem)
            
            with open('debug.log', 'a') as f:
                print(f"--- Processing {file_path} ---", file=f)
                print(json.dumps(result, indent=4), file=f)
            
            file_result = {
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'retry_button': '🔄 Retry'
            }

            if result['status'] == 'success':
                file_result['status'] = 'success'
                file_result['error'] = ''
                # Flatten the exercise data into the dict
                _flatten_results_to_row(result['data'], file_result)
            else:
                file_result['status'] = 'failed'
                file_result['error'] = result['error']
                file_result['grade'] = ''
                file_result['feedback'] = ''
                file_result['is_complete'] = False
                file_result['total_grade'] = 0
                file_result['max_score'] = 0

            results.append(file_result)
        
        # Create DataFrame
        df = pd.DataFrame(results)
        
        # Save to CSV
        output_path = os.path.join(folder_path, f'grading_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        
        # Get dynamic columns for CSV
        df_columns = _get_csv_columns(df)
        df[df_columns].to_csv(output_path, index=False, encoding='utf-8-sig')
        
        success_count = len([r for r in results if r['status'] == 'success'])
        failed_count = len([r for r in results if r['status'] == 'failed'])
        status_msg = f"✅ Processed {len(files)} submissions. Success: {success_count}, Failed: {failed_count}\nResults saved to: {output_path}"
        
        # Create display dataframe with buttons
        display_columns = ['file_name', 'status', 'grade', 'feedback', 'error', 'timestamp', 'retry_button']
        display_df = df[display_columns].copy()
        
        return status_msg, display_df, results, output_path
    
    except Exception as e:
        return f"❌ Error: {str(e)}", None, [], None


def _perform_grading_and_update_row(client, exercise_problem, results_data, row_index):
    """
    Internal helper function to grade a single file and update the results_data list in-place.
    Returns the status ('success' or 'failed')
    """
    file_info_to_update = results_data[row_index]
    file_path = file_info_to_update['file_path']
    
    result = grade_file(client, file_path, exercise_problem)

    with open('debug.log', 'a') as f:
        print(f"--- Retrying {file_path} ---", file=f)
        print(json.dumps(result, indent=4), file=f)

    # Clear old dynamic keys before adding new ones
    keys_to_remove = [k for k in file_info_to_update.keys() if k.startswith('ex_')]
    for k in keys_to_remove:
        del file_info_to_update[k]

    if result['status'] == 'success':
        file_info_to_update['status'] = 'success'
        file_info_to_update['error'] = ''
        # Flatten the exercise data into the dict
        _flatten_results_to_row(result['data'], file_info_to_update)
    else:
        file_info_to_update['status'] = 'failed'
        file_info_to_update['error'] = result['error']
        file_info_to_update['grade'] = ''
        file_info_to_update['feedback'] = ''
        file_info_to_update['is_complete'] = False
        file_info_to_update['total_grade'] = 0
        file_info_to_update['max_score'] = 0
    
    file_info_to_update['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return result['status']


def retry_single_grading(api_key, exercise_problem, results_data, csv_path, evt: gr.SelectData):
    """Retry grading a single file and update the CSV."""
    if not api_key:
        return None, "Please provide a Gemini API key", results_data, None
    
    if not exercise_problem.strip():
        return None, "Please ensure the exercise problem is still present", results_data, None
    
    row_index = evt.index[0]  # Get the row index from the click event
    col_index = evt.index[1]  # Get the column index
    
    # Column 6 is the retry button column (0-indexed)
    if col_index != 6: 
        return None, "Click on the '🔄 Retry' button to retry", results_data, None
    
    if not results_data or row_index >= len(results_data):
        return None, "Invalid file selection", results_data, None
    
    try:
        client = configure_gemini_client(api_key) 
        file_name = results_data[row_index]['file_name']

        status = _perform_grading_and_update_row(client, exercise_problem, results_data, row_index)
        
        # Update CSV
        df_save = pd.DataFrame(results_data)
        if csv_path and os.path.exists(os.path.dirname(csv_path)):
            # Get dynamic columns for CSV
            df_columns = _get_csv_columns(df_save)
            df_save[df_columns].to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # Create display for just the retried row
        retried_row_data = {
            'file_name': results_data[row_index]['file_name'],
            'status': results_data[row_index]['status'],
            'grade': results_data[row_index]['grade'],
            'feedback': results_data[row_index]['feedback'],
            'error': results_data[row_index]['error'],
            'timestamp': results_data[row_index]['timestamp'],
            'retry_button': '🔄 Retry'
        }
        retried_row_df = pd.DataFrame([retried_row_data])
        
        if status == 'success':
            status_msg = f"✅ Successfully re-graded {file_name}"
        else:
            status_msg = f"❌ Failed to re-grade {file_name}: {results_data[row_index]['error']}"
        
        return retried_row_df, status_msg, results_data, gr.update(visible=True)
    
    except Exception as e:
        return None, f"❌ Error during retry: {str(e)}", results_data, None

def retry_all_failed(api_key, exercise_problem, results_data, csv_path, progress=gr.Progress()):
    """Retry grading all failed files and update the CSV."""
    if not api_key:
        return "Please provide a Gemini API key", None, results_data
    
    if not exercise_problem.strip():
        return "Please ensure the exercise problem is still present", None, results_data
    
    if not results_data:
        return "No results to retry.", None, results_data
        
    try:
        client = configure_gemini_client(api_key)
        
        failed_indices = [i for i, row in enumerate(results_data) if row['status'] == 'failed']
        
        if not failed_indices:
            return "No failed submissions to retry.", None, results_data
            
        success_count = 0
        total_failed = len(failed_indices)
        
        for i, row_index in enumerate(failed_indices):
            file_name = results_data[row_index]['file_name']
            progress((i / total_failed), desc=f"Retrying {i + 1}/{total_failed}: {file_name}")
            
            try:
                status = _perform_grading_and_update_row(client, exercise_problem, results_data, row_index)
                if status == 'success':
                    success_count += 1
            except Exception as e:
                results_data[row_index]['status'] = 'failed'
                results_data[row_index]['error'] = f"Critical retry error: {str(e)}"
                
        # Update CSV
        df_save = pd.DataFrame(results_data)
        if csv_path and os.path.exists(os.path.dirname(csv_path)):
            # Get dynamic columns for CSV
            df_columns = _get_csv_columns(df_save)
            df_save[df_columns].to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # Create new full display dataframe
        display_columns = ['file_name', 'status', 'grade', 'feedback', 'error', 'timestamp', 'retry_button']
        display_df = df_save[display_columns].copy()
        
        status_msg = f"✅ Retried {total_failed} files. Success: {success_count}, Failed: {total_failed - success_count}"
        
        return status_msg, display_df, results_data

    except Exception as e:
        return f"❌ Error during mass retry: {str(e)}", None, results_data


# Create Gradio interface (Instructions updated)
with gr.Blocks(title="Gemini Automated Grading System", theme=gr.themes.Soft()) as app: # type: ignore
    gr.Markdown("# 🎓 Gemini Automated Grading System")
    gr.Markdown("Automatically grade multiple student submissions using Google's Gemini API")
    
    # State variables
    results_state = gr.State([])
    csv_path_state = gr.State(None)
    
    with gr.Row():
        with gr.Column(scale=2):
            api_key_input = gr.Textbox(
                label="Gemini API Key",
                placeholder="Enter your Gemini API key",
                type="password",
                value=os.environ.get("GEMINI_API_KEY")
            )
            folder_input = gr.Textbox(
                label="Submissions Folder Path",
                placeholder="Enter the path to the folder containing student submissions"
            )
            extensions_input = gr.Textbox(
                label="File Extensions to Grade",
                value=".pdf, .py, .txt",
                placeholder="Comma-separated list (e.g., .py, .pdf, .txt)"
            )
            exercise_problem_input = gr.Textbox(
                label="Exercise Problem Statement(s)",
                placeholder="Paste the full exercise problem(s) here. If there are multiple, list them clearly (e.g., using numbers 1., 2., 3.)...",
                lines=10
            )
            
            with gr.Row():
                process_btn = gr.Button("🚀 Grade Submissions", variant="primary", scale=2)
                # NEW "Retry All Failed" button
                retry_failed_btn = gr.Button("🔄 Retry All Failed", variant="secondary", scale=1)

        with gr.Column(scale=1):
            gr.Markdown("### Instructions")
            gr.Markdown("""
            1. Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
            2. Enter the folder path containing all student submissions.
            3. Specify the file extensions (e.g., `.py`, `.pdf`).
            4. Paste the **full exercise problem(s)** into the text box.
                - **Important:** If you have multiple exercises, list them clearly (e.g., "1. Do X", "2. Do Y"). The AI will grade each one.
            5. Click "Grade Submissions" to start.
            6. A CSV file with all results (including columns per exercise) will be saved in the submissions folder.
            7. Click the 🔄 **Retry** button on any *single* failed row to re-grade it.
            8. Click the 🔄 **Retry All Failed** button to re-grade *all* failed rows.
            """)
    
    status_output = gr.Textbox(label="Status", lines=2)
    
    gr.Markdown("### 📊 Grading Results")
    gr.Markdown("💡 **Tip**: Click on the '🔄 Retry' button in any failed row to retry that file.")
    
    results_df = gr.Dataframe(
        headers=["File Name", "Status", "Grade", "Feedback", "Error", "Timestamp", "Action"],
        label="Processing Results",
        wrap=True,
        interactive=True,
        column_widths=["15%", "8%", "10%", "35%", "15%", "12%", "5%"]
    )
    
    gr.Markdown("---")
    gr.Markdown("### 🔄 Last Retried File")
    
    retried_row_df = gr.Dataframe(
        headers=["File Name", "Status", "Grade", "Feedback", "Error", "Timestamp", "Action"],
        label="Last Retried File Result",
        wrap=True,
        interactive=False,
        visible=False,
        column_widths=["15%", "8%", "10%", "35%", "15%", "12%", "5%"]
    )
    
    # Event handlers
    process_btn.click(
        fn=process_submissions,
        inputs=[api_key_input, folder_input, extensions_input, exercise_problem_input],
        outputs=[status_output, results_df, results_state, csv_path_state]
    )
    
    # NEW handler for "Retry All Failed"
    retry_failed_btn.click(
        fn=retry_all_failed,
        inputs=[api_key_input, exercise_problem_input, results_state, csv_path_state],
        outputs=[status_output, results_df, results_state]
    )
    
    results_df.select(
        fn=retry_single_grading,
        inputs=[api_key_input, exercise_problem_input, results_state, csv_path_state],
        outputs=[retried_row_df, status_output, results_state, retried_row_df]
    )

if __name__ == "__main__":
    app.launch()