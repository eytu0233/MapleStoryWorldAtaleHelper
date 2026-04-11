import os
import cv2
from ultralytics import YOLO

INPUT_DIR = r"C:\Users\Steve\PycharmProjects\MapleStoryWorldAtaleZhTWChannelChange_claude\tool\dataset"
OUTPUT_DIR = "result"

model = YOLO("101_cd.pt")

os.makedirs(OUTPUT_DIR, exist_ok=True)

jpg_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".jpg")]

for filename in jpg_files:
    input_path = os.path.join(INPUT_DIR, filename)
    results = model.predict(input_path)

    img = cv2.imread(input_path)

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = f"{result.names[cls_id]} {conf:.2f}"

            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.putText(img, f"({x1},{y1})", (x1, y1 + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 255), 1)
            cv2.putText(img, f"({x2},{y2})", (x2 - 60, y2 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 255), 1)

    stem, ext = os.path.splitext(filename)
    output_path = os.path.join(OUTPUT_DIR, f"{stem}_result{ext}")
    cv2.imwrite(output_path, img)
    print(f"已輸出 {output_path}")
