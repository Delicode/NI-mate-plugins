/* Original code by Delicode Ltd (www.delicode.com) */
/* All modifications are allowed, but we encourage  */
/* sharing any beneficial modifications at the NI   */
/* mate forums (forum.ni-mate.com).	    			*/

using UnityEngine;
using System.Collections;
using System.Runtime.InteropServices;
using System;

public class NImateFeed : MonoBehaviour {
	[DllImport ("DelicodeUnityLibrary")]
		public static extern int getNImateFeed1(IntPtr data_ptr);
	[DllImport ("DelicodeUnityLibrary")]
		public static extern int getNImateFeed2(IntPtr data_ptr);
	
	Texture2D tex = null;
	IntPtr data_ptr;
	Color32[] pixels = null;
	byte[] bytes_array = null;
	
	public bool feed2 = false;
	public float tex_size = 0.2f;
	public float tex_x = 0.9f;
	public float tex_y = 0.9f;
	
	void Start ()
	{
		if(tex == null) {
			tex = new Texture2D(640,480,TextureFormat.ARGB32, false);
			tex.wrapMode = TextureWrapMode.Clamp;
			if(gameObject.GetComponent("GUILayer") == null)
				renderer.material.mainTexture = tex;
		}
		
		data_ptr = Marshal.AllocHGlobal(640*480*4*sizeof(byte));
		pixels = new Color32[640*480];
		bytes_array = new byte[640*480*4];
	}
	
	void Update ()
	{
		int ret = feed2 ? getNImateFeed2(data_ptr) : getNImateFeed1(data_ptr);
		
		if(ret == 1)
			print("Error: Couldn't open the NI mate feed.");
		else if(ret == 2)
			print("Error: Couldn't map the NI mate feed.");
		else {			
			Marshal.Copy(data_ptr, bytes_array, 0, 640*480*4*sizeof(byte));
			
			for(int i=0; i<640*480; i++)
				pixels[i] = new Color32(bytes_array[4*i+0], bytes_array[4*i+1], bytes_array[4*i+2], bytes_array[4*i+3]);
			
			tex.SetPixels32(pixels);
			tex.Apply();
		}
	}
	
	void OnGUI() {
		if(gameObject.GetComponent("GUILayer") != null) {
			float tex_w = tex.width * tex_size;
			float tex_h = tex.height * tex_size;
			Rect tex_rect = new Rect((Screen.width-tex_w)*tex_x, (Screen.height-tex_h)*tex_y, tex_w, tex_h);
			GUI.DrawTexture(tex_rect, tex, ScaleMode.ScaleToFit, true);
		}
	}
	
	void onDestroy()
	{
		Marshal.FreeHGlobal(data_ptr);
	}
}
