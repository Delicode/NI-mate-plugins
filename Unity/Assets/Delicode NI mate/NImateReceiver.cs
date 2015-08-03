/* Original code by Delicode Ltd (www.delicode.com) */
/* All modifications are allowed, but we encourage  */
/* sharing any beneficial modifications at the NI   */
/* mate forums (forum.ni-mate.com). 				*/

using UnityEngine;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Net;
using System.Net.Sockets;
using System.Threading;

public class NImateReceiver : MonoBehaviour {

	static UdpClient _reader = null;
	static Thread _thread;	
	static Hashtable _locations = null;
	static Hashtable _rotations = null;
	static Hashtable _original_rotations = null;
	Quaternion root_rotation;
	bool root_rotation_set = false;
	
	public int OSCport = 7000;
	public bool keepOriginalRotations = true;
	public bool useRootRotation = true;
	public bool startNImate = false;
	public bool quitNImate = false;
	public int quitPort = 7000;
	public String profileFile = "";
	
	byte[] SwapEndian(byte[] data)
	{
		byte[] swapped = new byte[data.Length];
		for(int i = data.Length - 1, j = 0 ; i >= 0 ; i--, j++)
		{
			swapped[j] = data[i];
		}
		return swapped;
	}
	
	float decodeFloat(byte[] bytes, int start)
	{
		byte[] val = new byte[4];
		
		Array.Copy(bytes, start, val, 0, 4);
		
		if(BitConverter.IsLittleEndian)
			val = SwapEndian(val);
		
		return BitConverter.ToSingle(val, 0);
	}
	
	Vector3 decodeLocation(byte[] bytes, int start)
	{
		float[] location = new float[3];
		
		for(int i=0; i<3; i++)
			location[i] = decodeFloat(bytes, start+4*i);
		
		return new Vector3(location[0], location[1], -location[2]);
	}
	
	Quaternion decodeQuaternion(byte[] bytes, int start)
	{
		float[] quaternion = new float[4];
		
		for(int i=0; i<4; i++)
			quaternion[i] = decodeFloat(bytes, start+4*i);
		
		return new Quaternion(quaternion[1], quaternion[2], -quaternion[3], quaternion[0]);
	}
	
	Quaternion decodeRotation(byte[] bytes, int start)
	{
		float[] matrix = new float[9];
		
		for(int i=0; i<9; i++)
			matrix[i] = decodeFloat(bytes, start+4*i);
		
		Vector3 forward_vec = new Vector3(-matrix[2], -matrix[5], matrix[8]);
		Vector3 up_vec = new Vector3(matrix[1], matrix[4], -matrix[7]);
		
		if(forward_vec.magnitude > 0)
			return Quaternion.LookRotation(forward_vec, up_vec);
		else
			return new Quaternion(0,0,0,0);
	}
	
	Hashtable decodeBytes(byte[] bytes)
	{
		Hashtable result = new Hashtable();
		if(bytes[0] == '#')
			return result;
		
		int start = 0;
		
		int count = 0;
		for(int index = 0; bytes[index] != 0; index++)
			count++;
		
		string address = Encoding.ASCII.GetString(bytes, start, count);
		
		start += count + 1;
		start = ((start + 3) / 4) * 4;
		
		if(bytes[start] == ',') {
			int float_count = 1;
			
			while(float_count < 12 && bytes[start+float_count] == 'f')
				float_count++;
			
			float_count -= 1;
			
			switch(float_count) {
			case 3:	//location
				result["address"] = address;
				result["location"] = decodeLocation(bytes, start+8);
				break;
			case 4: //quaternion
				result["address"] = address;
				result["rotation"] = decodeQuaternion(bytes, start+8);
				break;
			case 7: //location & quaternion
				result["address"] = address;
				result["location"] = decodeLocation(bytes, start+8);
				result["rotation"] = decodeQuaternion(bytes, start+20);
				break;
			case 9: //matrix
				result["address"] = address;
				result["rotation"] = decodeRotation(bytes, start+12);
				break;
			case 12: //location & matrix
				result["address"] = address;
				result["location"] = decodeLocation(bytes, start+16);
				result["rotation"] = decodeRotation(bytes, start+28);
				break;
			}
		}
		
		return result;
	}
	
	void ReceiveMessage()
	{
		while (true) {
			try {
				while(_reader.Available > 0) {
					byte[] bytes = new byte[1024];
					if(_reader.Client.Receive(bytes) > 0) {
						Hashtable decoded = decodeBytes(bytes);
						if(decoded.ContainsKey("address")) {
							lock(typeof(NImateReceiver)) {
								if(decoded.ContainsKey("location"))
									_locations[((String)decoded["address"])] = decoded["location"];
								else
									_locations.Remove((String)decoded["address"]);
								
								if(decoded.ContainsKey("rotation"))
									_rotations[((String)decoded["address"])] = decoded["rotation"];
								else
									_rotations.Remove((String)decoded["address"]);
							}
						}
					}
				}
			}
			catch (Exception e)
			{
				print(e.Message);
			}
			Thread.Sleep(33);
		}
	}
	
	void Start ()
	{	
		if(_reader == null) {
			try {
				_reader = new UdpClient(OSCport);
				print("NI mate receiver is listening to port " + OSCport + ".");
			}
			catch {
				throw new Exception("NI mate receiver couldn't open a udp client.");
			}

			_thread = new Thread(new ThreadStart(ReceiveMessage));
			_thread.IsBackground = true;
			_thread.Start();
			_locations = new Hashtable();
			_rotations = new Hashtable();
			_original_rotations = new Hashtable();
			root_rotation_set = false;
			
			if(startNImate && profileFile.Length > 0) {
				try {
					if(Environment.OSVersion.Platform == System.PlatformID.Unix || Environment.OSVersion.Platform == System.PlatformID.MacOSX)
						System.Diagnostics.Process.Start("open", "\"" + Application.dataPath + "/" + profileFile + "\"");
					else
						System.Diagnostics.Process.Start("\"" + Application.dataPath + "/" + profileFile + "\"");
				}
				catch {
					throw new Exception("NI mate receiver couldn't open: " + Application.dataPath + "/" + profileFile);
				}
			}
		}
	}
	
	void saveTrRotation(Transform tr)
	{
		if(!_original_rotations.ContainsKey(tr.name))
			_original_rotations[tr.name] = tr.rotation;
		
		Transform[] allChildren = tr.GetComponentsInChildren<Transform>();
		foreach (Transform child in allChildren) {
			if(!_original_rotations.ContainsKey(child.name))
				saveTrRotation(child);
		}
		
		if(root_rotation_set == false) {
			root_rotation_set = true;
			root_rotation = tr.root.rotation;
		}
	}
	
	void UpdateTrLocation(Transform tr)
	{
		if(tr.parent != null)
			UpdateTrLocation(tr.parent);
		
		if(_locations.ContainsKey(tr.name))
			tr.position = (Vector3)_locations[tr.name];
	}
	
	void UpdateTrRotation(Transform tr)
	{
		if(tr.parent != null)
			UpdateTrRotation(tr.parent);
		
		if(_rotations.ContainsKey(tr.name)) {
			if(keepOriginalRotations) {
				if(useRootRotation)
					tr.rotation = root_rotation * ((Quaternion)_rotations[tr.name]) * Quaternion.Inverse(root_rotation) * ((Quaternion)_original_rotations[tr.name]);
				else
					tr.rotation = ((Quaternion)_rotations[tr.name]) * ((Quaternion)_original_rotations[tr.name]);
			}
			else
				tr.rotation = (Quaternion)_rotations[tr.name];
		}
	}
	
	void Update ()
	{
		lock(typeof(NImateReceiver)) {
			foreach(DictionaryEntry de in _locations) {
				GameObject ob = GameObject.Find(de.Key as String);
				if(ob != null)
					UpdateTrLocation(ob.transform);
			}
			foreach(DictionaryEntry de in _rotations) {
				if(!_original_rotations.ContainsKey(de.Key)) {
					GameObject ob = GameObject.Find(de.Key as String);
					if(ob != null)
						saveTrRotation(ob.transform);
				}
			}
			foreach(DictionaryEntry de in _rotations) {
				GameObject ob = GameObject.Find(de.Key as String);
				if(ob != null && ((Quaternion)de.Value)[3] != 0)
					UpdateTrRotation(ob.transform);
			}
		}
	}
	
	void sendQuitNImate()
	{
		if(quitNImate) {
			Socket sock = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
			IPEndPoint endPoint = new IPEndPoint(IPAddress.Parse("127.0.0.1"), quitPort);
			byte[] quitCommand = new byte[]{0x2F, 0x4E, 0x49, 0x20, 0x6D, 0x61, 0x74, 0x65, 0x00, 0x00, 0x00, 0x00, 0x2C, 0x73, 0x00, 0x00, 0x71, 0x75, 0x69, 0x74, 0x00, 0x00, 0x00, 0x00};
			sock.SendTo(quitCommand, endPoint);
			sock.Close();
		}
	}
	
	void OnDisable()
	{
		if(_reader != null) {
			_thread.Abort();
			_reader.Close();
			_reader = null;
			
			sendQuitNImate();
			
			print("NI mate receiver stopped listening to port " + OSCport + ".");
		}
	}
	
	void OnDestroy()
	{
		if(_reader != null) {
			_thread.Abort();
			_reader.Close();
			_reader = null;
			
			sendQuitNImate();
			
			print("NI mate receiver stopped listening to port " + OSCport + ".");
		}
	}
}
