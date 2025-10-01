using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class DataLogSdk
{
    public string id;    
    public DateTime? timestamp;
    public string project;
    public string level;
    public List<string> tags;
    public string message;
    public object data;
    public string request_id;

    public DataLogSdk() { }

}
