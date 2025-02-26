import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageOps
import subprocess
import threading
import cv2
import io

class VideoConverterApp:
	def __init__(self, root):
		self.root = root
		self.root.title("Fisheye to Rectilinear Converter")

		self.video_path = None
		self.video_duration = 0
		self.frame_count = 0

		self.ffmpeg_thread = None

		self.last_menu_update = None

		self.create_widgets()

	def create_widgets(self):
		### LEFT MENU FRAME ###
		self.menu_frame = tk.Frame(self.root, width=200)
		self.menu_frame.pack(side="left", fill="y")

		# Load Video Button (at the top)
		self.load_button = tk.Button(self.menu_frame, text="Load Video", command=self.load_video)
		self.load_button.pack(pady=10, padx=10, fill="x")

		# v360 Settings Frame
		settings_frame = tk.LabelFrame(self.menu_frame, text="v360 Filter Settings", padx=10, pady=5)
		settings_frame.pack(padx=10, pady=5, fill="x")

		tk.Label(settings_frame, text="Input FOV").grid(row=0, column=0, sticky="w")
		self.in_fov_slider = tk.Scale(settings_frame, from_=90, to=180, orient=tk.HORIZONTAL, command=self.menu_updated)
		self.in_fov_slider.set(180)
		self.in_fov_slider.grid(row=0, column=1, padx=5, pady=2)

		tk.Label(settings_frame, text="Output FOV").grid(row=1, column=0, sticky="w")
		self.out_fov_slider = tk.Scale(settings_frame, from_=60, to=180, orient=tk.HORIZONTAL, command=self.menu_updated)
		self.out_fov_slider.set(90)
		self.out_fov_slider.grid(row=1, column=1, padx=5, pady=2)

		# Crop Settings Frame
		crop_frame = tk.LabelFrame(self.menu_frame, text="Crop Settings", padx=10, pady=5)
		crop_frame.pack(padx=10, pady=5, fill="x")

		tk.Label(crop_frame, text="Crop Width Fraction").grid(row=0, column=0, sticky="w")
		self.crop_w_entry = tk.Scale(crop_frame, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL, command=self.menu_updated)
		self.crop_w_entry.set(1)
		self.crop_w_entry.grid(row=0, column=1, padx=5, pady=2)

		tk.Label(crop_frame, text="Crop Height Fraction").grid(row=1, column=0, sticky="w")
		self.crop_h_entry = tk.Scale(crop_frame, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL, command=self.menu_updated)
		self.crop_h_entry.set(1)
		self.crop_h_entry.grid(row=1, column=1, padx=5, pady=2)

		# Export Button (at the bottom)
		self.export_button = tk.Button(self.menu_frame, text="Export Video", command=self.export_video)
		self.export_button.pack(side="bottom", pady=10, padx=10, fill="x")

		### RIGHT PREVIEW FRAME ###
		self.preview_frame = tk.Frame(self.root)
		self.preview_frame.pack(side="right", fill="both", expand=True)

		# Canvas for Video Preview
		self.canvas = tk.Canvas(self.preview_frame, width=640, height=480, bg="black")
		self.canvas.pack(padx=10, pady=5)

		# Timeline Slider (Scrubber)
		self.timeline_slider = tk.Scale(
			self.preview_frame, from_=0, to=100, resolution=1, orient=tk.HORIZONTAL, label="Scrub Frame",
			command=self.menu_updated, length=640
		)
		self.timeline_slider.pack(padx=10, pady=5)

	def load_video(self):
		self.video_path = filedialog.askopenfilename(
			title="Select Video File",
			filetypes=[("Video files", "*.mp4 *.mov *.avi"), ("All files", "*.*")]
		)
		if self.video_path:
			cap = cv2.VideoCapture(self.video_path)
			if cap.isOpened():
				# Calculate video duration in seconds
				fps = cap.get(cv2.CAP_PROP_FPS)
				frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
				self.frame_count = int(frame_count)
				self.video_duration = frame_count / fps if fps > 0 else 0
				self.timeline_slider.config(to=frame_count-1)
				cap.release()
				self.update_preview_frame(0)

	def menu_updated(self, _):
		# Called when any menu slider is updated
		if self.last_menu_update:
			self.root.after_cancel(self.last_menu_update)  # Cancel previous pending calls

		def start_preview_update():
			frame = int(self.timeline_slider.get())
			self.start_ffmpeg_thread(frame)

		# Debounce updates to avoid excessive FFmpeg calls
		self.last_menu_update =  self.root.after(50, start_preview_update)

	def start_ffmpeg_thread(self, frame: int):
		# Runs FFmpeg command in a separate thread
		if self.ffmpeg_thread and self.ffmpeg_thread.is_alive():
			return  # Don't start a new thread if one is still running

		self.ffmpeg_thread = threading.Thread(target=self.update_preview_frame, args=(frame,), daemon=True)
		self.ffmpeg_thread.start()

	def build_filter(self):
		# Construct the v360 filter string using current slider values
		in_fov = self.in_fov_slider.get()
		out_fov = self.out_fov_slider.get()
		filter_str = f"v360=input=fisheye:output=rectilinear:id_fov={in_fov}:d_fov={out_fov}"

		# Append crop filter if crop fields are provided
		crop_w = self.crop_w_entry.get()
		crop_h = self.crop_h_entry.get()
		if crop_w and crop_h:
			filter_str += f",crop=iw*{crop_w}:ih*{crop_h}:(iw - iw*{crop_w}) / 2:(ih - ih*{crop_h}) / 2"
		return filter_str

	def update_preview_frame(self, frame: int):
		if not self.video_path:
			return

		filter_str = self.build_filter()
		# Build ffmpeg command to extract one frame at the given time with v360 applied
		cmd = [
			"ffmpeg",
			"-hide_banner",
			"-loglevel", "error",
			"-ss", str((frame/self.frame_count)*self.video_duration),
			"-i", self.video_path,
			"-frames:v", "1",
			"-vf", filter_str,
			"-f", "image2pipe",
			"-vcodec", "png",
			"pipe:1"
		]
		
		try:
			proc = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
			if proc.returncode == 0 and proc.stdout:
				image_data = proc.stdout
				image = Image.open(io.BytesIO(image_data))
				# Resize preview for display purposes
				image = ImageOps.pad(image, (640, 480), color="black")
				self.photo = ImageTk.PhotoImage(image)
				
				def update_image():
					self.canvas.delete("all")
					self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

				# Update UI on the main thread
				self.root.after(0, update_image)
			else:
				print("Error in FFmpeg preview extraction:", proc.stderr.decode())
		except Exception as e:
			print("Exception during preview update:", e)

	def export_video(self):
		if not self.video_path:
			return

		output_path = filedialog.asksaveasfilename(
			title="Save Video As",
			defaultextension=".mp4",
			filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
		)
		if not output_path:
			return

		filter_str = self.build_filter()
		# Build FFmpeg command to process the entire video with the given filters
		cmd = [
			"ffmpeg",
			"-hide_banner",
			"-loglevel", "error",
			"-i", self.video_path,
			"-vf", filter_str,
			"-c:a", "copy",  # Copy audio without re-encoding
			output_path
		]
		print("Exporting video with command:")
		print(" ".join(cmd))
		try:
			subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
			print("Export complete!")
		except subprocess.CalledProcessError as e:
			print("Error during export:", e)

if __name__ == "__main__":
	root = tk.Tk()
	app = VideoConverterApp(root)
	root.mainloop()
