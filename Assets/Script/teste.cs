using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;

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

    struct ListaAditional
    {
        public string user;
        public string ip;
    }

    public void SaveALogStart()
    {
        List<String> tags = new List<String>();
        tags.Add("start");
        StartCoroutine(LogSaver.SaveLog("INICIANDO_PROCESSO", "INFO", tags));
    }

    public void SaveALogCadastro()
    {
        List<String> tags = new List<String>();
        tags.Add("auth");
        tags.Add("login");
        ListaAditional listaAditional = new ListaAditional();
        listaAditional.user = "0678";
        listaAditional.ip = "192.168.215.8";
        StartCoroutine(LogSaver.SaveLog("CADASTRO_EFETUADO", "INFO", tags, JsonConvert.SerializeObject(listaAditional)));
    }

    public void SaveALogFinal()
    {
        List<String> tags = new List<String>();
        tags.Add("finish");
        StartCoroutine(LogSaver.SaveLog("FINALIZANDO_PROCESSO", "INFO", tags));
    }

    // void SaveLog(string message, string level, List<string> tags, string additional = "")
    // {
    //     StartCoroutine(SaveLogCoroutine(message, level, tags, additional));
    // }

    // IEnumerator SaveLogCoroutine(string message, string level, List<string> tags, string additional = "")
    // {
    //     yield return LogUtilSdk.GetDatalogFromJsonCoroutine((dataLog) =>
    //     {
    //         if (dataLog != null)
    //         {
    //             dataLog.message = message;
    //             dataLog.level = level;
    //             dataLog.tags.AddRange(tags);
    //             if (additional != "")
    //                 dataLog.data = JsonConvert.DeserializeObject(additional);
    //             else
    //                 dataLog.data = new object();
    //             LogUtilSdk.SaveLogToJson(dataLog);
    //         }
    //         else
    //         {
    //             Debug.LogError("Erro ao carregar o DataLog do JSON.");
    //         }
    //     });
    // }



}
