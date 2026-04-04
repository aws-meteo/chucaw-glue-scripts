#!/bin/bash
# scripts/batch_process_gribs.sh

set -e

SOURCE_DIR="/mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/scripts/glue_jobs/test_grib"
BASE_OUT_DIR="/mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/test_output_parquet"

echo "=========================================================="
echo "Iniciando Automatización y Conversión Masiva a PyArrow..."
echo "=========================================================="

for filepath in $(ls "$SOURCE_DIR"/*.grib2); do
    filename=$(basename "$filepath")
    
    horizon=$(echo "$filename" | cut -d'-' -f2)
    date_str=$(echo "$filename" | cut -d'-' -f1 | cut -c 1-8)
    
    OUT_DIR="$BASE_OUT_DIR/$horizon"
    mkdir -p "$OUT_DIR"
    
    echo "▶ Procesando $filename"
    echo "  - Horizonte: $horizon"
    echo "  - Fecha Particion: $date_str"
    echo "  - Salida: $OUT_DIR"
    
    /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/.venv311-linux/bin/python /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/scripts/glue_jobs/grib_to_platinum_parquet.py \
        --GRIB_PATH "$filepath" \
        --OUTPUT_DIR "$OUT_DIR" \
        --DATE "$date_str" \
        --RUN "$horizon"
        
    echo "  [✓] Particiones creadas con éxito"
    
    echo "  ▶ Ejecutando validación de Checksum y generación de imágenes..."
    /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/.venv311-linux/bin/python /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts/scripts/verify_parquet_images.py \
        --grib "$filepath" \
        --parquet-dir "$OUT_DIR" \
        --date "$date_str" \
        --run "$horizon" \
        --out "$OUT_DIR/visual_qa"
    
    echo "  [✓] QA Integral Sorteado Exitosamente"
    echo "----------------------------------------------------------"
done

echo "🎉 PROCESAMIENTO BATCH INTERNACIONAL FINALIZADO CON ÉXITO."
