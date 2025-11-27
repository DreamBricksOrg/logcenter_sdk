using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;

public class LogSaver : MonoBehaviour
{   
    public static IEnumerator SaveLog(string message, string level, List<string>? tags = null, string additional = "")
    {
        yield return LogUtilSdk.GetDatalogFromJsonCoroutine((dataLog) =>
        {
            if (dataLog != null)
            {
                dataLog.message = message;
                dataLog.level = level;
                dataLog.tags.AddRange(tags ?? new List<string>());
                if (additional != "")
                    dataLog.data = JsonConvert.DeserializeObject(additional);
                else
                    dataLog.data = new object();
                LogUtilSdk.SaveLogToJson(dataLog);
            }
            else
            {
                Debug.LogError("Erro ao carregar o DataLog do JSON.");
            }
        });
    }



}
