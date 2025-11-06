import unicodedata
from pathlib import Path
from docx2pdf import convert
import sys
import time

def normalize_name(name: str) -> str:
    """
    Converts any non-ASCII characters to their closest ASCII equivalent
    and replaces spaces with underscores.
    
    Example: "một trái.docx" -> "mot_trai.docx"
    Example: "Đỗ.docx" -> "Do.docx"
    """
    # Manually replace the Vietnamese 'D' characters FIRST.
    # These are not decomposed by unicodedata.
    name = name.replace('Đ', 'D')
    name = name.replace('đ', 'd')
    
    # Decompose characters (e.g., 'ỗ' -> 'o' + '̂' + '̃')
    # We use NFD (Normalization Form D) here.
    nfd_form = unicodedata.normalize('NFD', name)
    
    # Encode to ASCII, ignoring non-ASCII bytes (the diacritics),
    # then decode back to a string.
    ascii_name = nfd_form.encode('ascii', 'ignore').decode('ascii')
    
    # Replace spaces with underscores
    normalized_name = ascii_name.replace(' ', '_')
    
    return normalized_name

def process_directory(input_dir_str: str, output_dir_str: str):
    """
    Recursively finds all .docx files in the input directory,
    converts them to PDF, and saves them in the output directory
    with a mirrored, normalized folder structure.
    """
    
    input_dir = Path(input_dir_str)
    output_dir = Path(output_dir_str)
    
    if not input_dir.is_dir():
        print(f"Error: Input directory not found: {input_dir}")
        return
        
    # Ensure the base output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting conversion...")
    print(f"  Input: {input_dir}")
    print(f"  Output: {output_dir}\n")
    
    start_time = time.time()
    converted_count = 0
    failed_count = 0
    
    # Use rglob('*.docx') to recursively find all .docx files
    docx_files = list(input_dir.rglob('*.docx'))
    
    if not docx_files:
        print("No .docx files found in the input directory.")
        return
        
    print(f"Found {len(docx_files)} .docx files to process.")

    for docx_path in docx_files:
        try:
            # 1. Get the path relative to the input directory
            # e.g., "C:/me/doc1/một_trái.docx" -> "doc1/một_trái.docx"
            relative_path = docx_path.relative_to(input_dir)
            
            # 2. Normalize the directory parts
            # e.g., "doc1/sub folder" -> ["doc1", "sub_folder"]
            normalized_dir_parts = [normalize_name(part) for part in relative_path.parent.parts]
            
            # 3. Normalize the file's base name (without extension)
            # e.g., "một_trái" -> "mot_trai"
            normalized_base_name = normalize_name(docx_path.stem)
            
            # 4. Create the new PDF filename
            # e.g., "mot_trai.pdf"
            pdf_filename = normalized_base_name + ".pdf"
            
            # 5. Combine the parts to create the final output path
            # e.g., Path("C:/output_me") / "doc1" / "mot_trai.pdf"
            final_output_path = output_dir.joinpath(*normalized_dir_parts, pdf_filename)
            
            # 6. Ensure the target directory exists
            # e.g., "C:/output_me/doc1"
            final_output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 7. Perform the conversion
            print(f"\nProcessing: {docx_path}")
            print(f"  -> Output: {final_output_path}")
            
            # str() is used because docx2pdf expects string paths
            convert(str(docx_path), str(final_output_path))
            
            print("  -> Success.")
            converted_count += 1
            
        except Exception as e:
            print(f"  -> [ERROR] Failed to convert {docx_path}: {e}")
            failed_count += 1

    # --- Summary ---
    end_time = time.time()
    print("\n" + "="*30)
    print("Conversion Complete")
    print(f"Total time: {end_time - start_time:.2f} seconds")
    print(f"Successfully converted: {converted_count}")
    print(f"Failed: {failed_count}")
    print("="*30)


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Please change these paths to match your system
    
    # Windows example:
    # INPUT_DIRECTORY = r"C:\Users\YourUser\Documents\MyDocRoot"
    # OUTPUT_DIRECTORY = r"C:\Users\YourUser\Documents\MyPdfOutput"
    
    # macOS/Linux example:
    # INPUT_DIRECTORY = "/Users/youruser/Documents/MyDocRoot"
    # OUTPUT_DIRECTORY = "/Users/youruser/Documents/MyPdfOutput"

    # Set your directories here:
    INPUT_DIRECTORY = "input_folder"  # <--- SET YOUR INPUT FOLDER
    OUTPUT_DIRECTORY = "output_folder" # <--- SET YOUR OUTPUT FOLDER

    # --- END CONFIGURATION ---

    # You can also use command-line arguments to pass paths
    # e.g., python convert_docx_to_pdf.py "C:/me" "C:/output_me"
    if len(sys.argv) == 3:
        INPUT_DIRECTORY = sys.argv[1]
        OUTPUT_DIRECTORY = sys.argv[2]
        
    process_directory(INPUT_DIRECTORY, OUTPUT_DIRECTORY)