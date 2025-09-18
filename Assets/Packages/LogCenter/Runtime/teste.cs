using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class teste : MonoBehaviour
{
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {

    }

    // Update is called once per frame
    void Update()
    {

    }

    public void SaveALog()
    {
        List<String> tags = new List<String>();
        tags.Add("Teste");
        SaveLog("TESTE_FUNCIONAMENTO", "INFO", tags);
    }

    void SaveLog(string status, string level, List<string>tags, string additional = "")
    {
        StartCoroutine(SaveLogCoroutine(status, level, tags, additional));
    }

    IEnumerator SaveLogCoroutine(string message, string level, List<string>tags, string additional = "")
    {
        yield return LogUtil.GetDatalogFromJsonCoroutine((dataLog) =>
        {
            if (dataLog != null)
            {
                dataLog.message = message;
                dataLog.level = level;
                dataLog.tags.AddRange(tags);
                dataLog.data = additional;
                LogUtil.SaveLogToJson(dataLog);
            }
            else
            {
                Debug.LogError("Erro ao carregar o DataLog do JSON.");
            }
        });
    }



}
