# Phase 1 feasibility spike (not SDK code). Requires: numpy scipy onnxruntime pyrnnoise webrtc-noise-gain,
# and silero_vad.onnx extracted from the silero-vad wheel to /tmp/silero. Results: docs/PHASE1_TECHNICAL_PLAN.md §5.
import ctypes, time, numpy as np, onnxruntime as ort
from scipy.signal import resample_poly, correlate
import pyrnnoise.rnnoise as R  # only to locate librnnoise.so
from webrtc_noise_gain import AudioProcessor
rng=np.random.default_rng(0)
def speechlike(sr,secs):
    t=np.arange(int(sr*secs))/sr; f0=140+30*np.sin(2*np.pi*0.7*t)
    ph=2*np.pi*np.cumsum(f0)/sr; s=sum(np.sin(k*ph)/k for k in range(1,12))
    env=(np.sin(2*np.pi*3.5*t)>0).astype(float)*(t%2<1.4)  # syllables + pauses
    return (0.3*s*env/np.abs(s).max()).astype(np.float32)
def snr(ref,x): return 10*np.log10(np.sum(ref**2)/np.sum((ref-x)**2)+1e-12)
def align(ref,x):
    lag=np.argmax(correlate(x[:48000],ref[:48000],'full'))-47999; lag=max(lag,0)
    return ref[:len(x)-lag], x[lag:]
out={}
# --- RNNoise 48k, 10ms frames, via raw ctypes
lib=ctypes.CDLL(R.LIBRNNOISE); lib.rnnoise_create.restype=ctypes.c_void_p
lib.rnnoise_process_frame.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_float)]
lib.rnnoise_process_frame.restype=ctypes.c_float
clean=speechlike(48000,10)
for nl in (0.02,0.05,0.1):
    noisy=clean+nl*rng.standard_normal(len(clean)).astype(np.float32)
    st=lib.rnnoise_create(None); y=np.empty_like(noisy); ts=[]
    for i in range(0,len(noisy)-479,480):
        f=(noisy[i:i+480]*32768).astype(np.float32); o=np.empty(480,np.float32)
        t0=time.perf_counter(); lib.rnnoise_process_frame(st,o.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),f.ctypes.data_as(ctypes.POINTER(ctypes.c_float))); ts.append(time.perf_counter()-t0)
        y[i:i+480]=o/32768
    a,b=align(clean,y); out[f"rnnoise noise={nl}"]=(snr(clean,noisy),snr(a,b),np.median(ts)*1e3,np.percentile(ts,99)*1e3)
# --- WebRTC NS+AGC 16k, 10ms
c16=resample_poly(clean,1,3).astype(np.float32)
for nl in (0.02,0.05,0.1):
    n16=c16+nl*rng.standard_normal(len(c16)).astype(np.float32)
    ap=AudioProcessor(0,3); y=[]; ts=[]
    for i in range(0,len(n16)-159,160):
        b=(np.clip(n16[i:i+160],-1,1)*32767).astype(np.int16).tobytes()
        t0=time.perf_counter(); r=ap.Process10ms(b); ts.append(time.perf_counter()-t0)
        y.append(np.frombuffer(r.audio,np.int16)/32767)
    y=np.concatenate(y).astype(np.float32); a,b=align(c16,y)
    out[f"webrtc-ns noise={nl}"]=(snr(c16,n16),snr(a,b),np.median(ts)*1e3,np.percentile(ts,99)*1e3)
# --- Silero VAD ONNX (no torch), 16k, 32ms windows
so=ort.SessionOptions(); so.intra_op_num_threads=1; so.inter_op_num_threads=1
sess=ort.InferenceSession("/tmp/silero/silero_vad/data/silero_vad.onnx",so,providers=["CPUExecutionProvider"])
state=np.zeros((2,1,128),np.float32); ctx=np.zeros((1,64),np.float32); probs=[]; ts=[]
n16=c16+0.02*rng.standard_normal(len(c16)).astype(np.float32)
for i in range(0,len(n16)-511,512):
    x=np.concatenate([ctx,n16[None,i:i+512]],1)
    t0=time.perf_counter(); p,state=sess.run(None,{"input":x,"state":state,"sr":np.array(16000,np.int64)}); ts.append(time.perf_counter()-t0)
    ctx=x[:,-64:]; probs.append(float(p[0,0]))
t=np.arange(len(probs))*512/16000; truth=np.array([(np.sin(2*np.pi*3.5*(tt+0.016))>0) and (tt%2<1.4) for tt in t])
print("== feasibility spike (2 vCPU x86_64, Python 3.13)")
for k,(a,b,m,p99) in out.items(): print(f"{k:22} SNR in {a:6.1f} dB -> out {b:6.1f} dB | per-10ms-frame median {m:.3f} ms p99 {p99:.3f} ms")
pr=np.array(probs); print(f"silero-vad onnx         per-32ms-window median {np.median(ts)*1e3:.3f} ms p99 {np.percentile(ts,99)*1e3:.3f} ms | mean p(speech) on speech {pr[truth].mean():.2f} vs non-speech {pr[~truth].mean():.2f}")
