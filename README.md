# אפליקציית ניטור קווי תקשורת

אפליקציה לניטור קווי תקשורת עם התראות בזמן אמת.

## 📋 תכונות

- 🔍 ניטור קווי תקשורת באמצעות ping
- 📊 טבלת התראות בזמן אמת
- 🎯 שתי גרסאות: רגילה ומצב התאוששות
- 📱 ממשק משתמש בעברית
- 🔧 קבצי קונפיגורציה נפרדים

## 🚀 התקנה

### דרישות מערכת
- Python 3.8+
- PySide6
- Git

### התקנת תלויות
```bash
pip install PySide6 pyinstaller
```

## 📁 מבנה הפרויקט

```
monitor_app/
├── app/                    # קוד מקור גרסה רגילה
├── recovery_version/       # קוד מקור גרסה עם התאוששות
├── config.json            # קונפיגורציה גרסה רגילה
├── sites.csv              # רשימת אתרים לניטור
├── run.bat                # סקריפט הפעלה
└── README.md              # קובץ זה
```

## 🔄 שתי הגרסאות

### גרסה רגילה (`app/`)
- התראות נמחקות מיד כשהתקשורת חוזרת
- צבע אדום/כתום לתקלות

### גרסה עם התאוששות (`recovery_version/`)
- התראות מסתמנות בירוק כשהתקשורת חוזרת
- נשארות 7 דקות לפני שנמחקות
- מאפשרת מעקב אחרי "החלמה" של הקווים

## 🏗️ בניית Executable

### גרסה רגילה:
```bash
cd monitor_app
python -m PyInstaller monitor.spec
# התוצאה: dist/monitor.exe
```

### גרסה עם התאוששות:
```bash
cd monitor_app/recovery_version
python -m PyInstaller monitor.spec
# התוצאה: dist/monitor.exe
```

## ⚙️ קבצי קונפיגורציה

### config.json (גרסה רגילה)
```json
{
  "recovery_mode": {
    "enabled": false,
    "keep_alert_minutes": 7
  }
}
```

### config.json (גרסה עם התאוששות)
```json
{
  "recovery_mode": {
    "enabled": true,
    "keep_alert_minutes": 7
  }
}
```

## 📄 קובץ sites.csv

פורמט: `SiteName,MainLineCode,MainIP,BackupLineCode,BackupIP,enabled`

דוגמה:
```
SiteName,MainLineCode,MainIP,BackupLineCode,BackupIP,enabled
חורה,1001,8.8.8.8,2001,1.1.1.1,1
יורה,1002,192.0.2.10,,,0
```

## 🎮 שימוש

1. הפעל את `run.bat` או `python app/main.py`
2. האפליקציה תתחיל לנטר אוטומטית
3. התראות יופיעו בטבלה עם צבעים:
   - 🔴 אדום: תקלה קריטית
   - 🟠 כתום: תקלה לא קריטית
   - 🟢 ירוק: התאוששות (רק בגרסה עם התאוששות)

## 📊 לוגים

לוגים נשמרים בתיקיית `logs/monitor.log`

## 🔧 פיתוח

### הוספת גרסה חדשה:
1. העתק תיקיית `app/` לתיקייה חדשה
2. שנה את הקוד לפי הצורך
3. עדכן את `config.json`
4. בנה executable חדש

## 📝 רישיון

פרויקט זה מיועד לשימוש פנימי.

## 🤝 תרומה

לשאלות או בעיות, פנה למפתח.