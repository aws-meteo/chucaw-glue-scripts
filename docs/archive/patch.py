import re
from pathlib import Path

path = Path('src/chucaw_preprocessor/ecmwf.py')
text = path.read_text(encoding='utf-8')

# Remove build_parquet_frames
pattern = re.compile(r'def build_parquet_frames\(ds: xr\.Dataset\) -> tuple\[pd\.DataFrame, pd\.DataFrame\]:.*?return surface, upper\n\n\n', re.DOTALL)
text = pattern.sub('', text)

# Remove write_parquet_frames
pattern2 = re.compile(r'def write_parquet_frames\(surface_df: pd\.DataFrame, upper_df: pd\.DataFrame, output_dir: str\) -> tuple\[str, str\]:.*?(?=def serialize_parquet_chunked|$)', re.DOTALL)
text = pattern2.sub('\n', text)

path.write_text(text, encoding='utf-8')
print("Cleaned up old methods.")
