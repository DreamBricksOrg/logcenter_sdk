using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class DataLogSdk
{
    public string project_id;    
    public string status;
    public string level;
    public string message;
    public string? timestamp;
    public List<string> tags;
    public object data;
    public string request_id;

    public DataLogSdk() { }

}
