using System;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;

public class LogUtil : MonoBehaviour
{
    private static string logFilePath;
    private static ConfigManager config;

    public class DataLogList
    {
        public List<DataLog> logs = new List<DataLog>();
    }
    public static void SaveLogToJson(DataLog dataLog)
    {

        string folderPath = Path.Combine(Application.persistentDataPath, "data_logs");

        if (!Directory.Exists(folderPath))
        {
            Directory.CreateDirectory(folderPath);
        }

        string logFilePath = Path.Combine(folderPath, "data_logs.json");

        List<DataLog> logList = new List<DataLog>();

        if (File.Exists(logFilePath))
        {
            string existingJson = File.ReadAllText(logFilePath);
            if (!string.IsNullOrWhiteSpace(existingJson))
            {
                logList = JsonConvert.DeserializeObject<List<DataLog>>(existingJson);
            }
        }

        dataLog.timestamp = DateTime.Now;
        logList.Add(dataLog);

        string newJson = JsonConvert.SerializeObject(logList, Formatting.Indented); // 'true' for pretty-print
        File.WriteAllText(logFilePath, newJson);


        Debug.Log("Log saved at " + logFilePath);
    }
    public static IEnumerator GetDatalogFromJsonCoroutine(Action<DataLog> onComplete)
    {
        config = new();
        DataLog dataLog = new DataLog();
        dataLog.id = config.GetValue("Json", "id");
        dataLog.project = config.GetValue("Json", "project");
        onComplete?.Invoke(dataLog);
        yield return null;
    }
}
