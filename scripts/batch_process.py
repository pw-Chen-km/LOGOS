
import subprocess
import os

papers = [
    ("https://openreview.net/pdf?id=WnW0zndglL", "output_WnW0zndglL"),
    ("https://arxiv.org/pdf/2602.12014.pdf", "output_2602_12014v1"),
    ("https://arxiv.org/pdf/1802.01561.pdf", "output_1802_01561"),
    ("https://arxiv.org/pdf/2602.20492.pdf", "output_2602_20492"),
    ("https://arxiv.org/pdf/2503.03438.pdf", "output_2503_03438")
]

for url, out_dir in papers:
    print(f"\n>>> Processing {url} into {out_dir}...")
    abs_out_dir = os.path.abspath(out_dir)
    cmd = [
        "conda", "run", "-n", "kgrag", 
        "python", "run_phase2.py", 
        url, abs_out_dir
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error processing {url}: {e}")
