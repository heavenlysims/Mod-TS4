import csv, re, threading, webbrowser
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SOURCE_URL = "https://sims4life.gg/sims-4-mod-status/"
SOURCE_NAME = "Sims4Life — Mod Status"
EXTS = {".package", ".ts4script"}

class StatusParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows=[]; self.row=None; self.cell=None; self.in_table=False
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=="table": self.in_table=True
        if not self.in_table: return
        if tag=="tr": self.row=[]
        elif tag in ("td","th") and self.row is not None: self.cell=[]
        elif tag=="a" and self.cell is not None:
            href=attrs.get("href")
            if href: self.cell.append(("LINK",href))
    def handle_data(self, data):
        if self.in_table and self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if not self.in_table: return
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            text=" ".join(x for x in self.cell if isinstance(x,str))
            links=[x[1] for x in self.cell if isinstance(x,tuple) and x[0]=="LINK"]
            self.row.append((re.sub(r"\s+"," ",text).strip(), links[0] if links else ""))
            self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row=None
        elif tag=="table": self.in_table=False

def fetch_statuses():
    req=Request(SOURCE_URL,headers={"User-Agent":"Mozilla/5.0 CelyModChecker/1.1"})
    with urlopen(req,timeout=20) as response:
        html=response.read().decode("utf-8","replace")
    parser=StatusParser(); parser.feed(html)
    records=[]
    for row in parser.rows:
        cells=[x[0] for x in row]
        if len(cells)<3: continue
        name=cells[0]
        if name.lower() in ("mod",""): continue
        status_idx=next((i for i,x in enumerate(cells) if x.lower() in ("works","broken","not checked","waiting for creator","waiting")),None)
        if status_idx is None: continue
        status=cells[status_idx].lower()
        link=next((u for _,u in row if u),SOURCE_URL)
        if link.startswith("/"):
            link="https://sims4life.gg"+link
        elif not link.startswith("http"):
            link=SOURCE_URL
        desc=" | ".join(cells[1:status_idx]) if status_idx>1 else ""
        records.append({"name":name,"status":status,"source":link or SOURCE_URL,"notes":desc})
    if not records:
        raise RuntimeError("La pagina online è cambiata o non ha restituito la tabella attesa.")
    return records

def norm(s):
    s=Path(s).stem.casefold()
    s=re.sub(r'\b(v|ver|version|update|updated)\s*[\d._-]+',' ',s)
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def map_status(r):
    s=r["status"]
    if s=="works": return "COMPATIBILE (fonte)"
    if s=="broken": return "ROTTA/OBSOLETA (fonte)"
    if s in ("waiting for creator","waiting"): return "IN ATTESA (fonte)"
    return "NON VERIFICATA (fonte)"

def match_status(filename, records):
    f=norm(filename)
    candidates=[]
    for r in records:
        n=norm(r["name"])
        if not n: continue
        if n in f or f in n:
            candidates.append((len(n),r))
    if candidates:
        r=max(candidates,key=lambda x:x[0])[1]
        return map_status(r),r["source"],r["notes"],r["name"]
    ft=set(f.split()); best=None
    for r in records:
        nt=set(norm(r["name"]).split()); common=ft & nt
        if len(common)>=2:
            score=len(common)/(len(ft|nt) or 1)
            if best is None or score>best[0]: best=(score,r)
    if best and best[0]>=0.5:
        r=best[1]
        return map_status(r),r["source"],r["notes"],r["name"]
    return "NON TROVATA NEL DATABASE",SOURCE_URL,"Nessuna corrispondenza sicura. Non significa che la mod sia obsoleta.",""

def scan(folder, records):
    out=[]
    for p in Path(folder).rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS: continue
        try:
            st=p.stat()
            status,source,notes,matched=match_status(p.name,records)
            out.append({"file":p.name,"path":str(p.relative_to(folder)),"type":p.suffix.lower(),
              "modified":datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
              "size_bytes":st.st_size,"status":status,"matched_mod":matched,
              "source":source,"notes":notes})
        except OSError as e:
            out.append({"file":p.name,"path":str(p),"type":p.suffix.lower(),"modified":"",
              "size_bytes":0,"status":"ERRORE LETTURA","matched_mod":"","source":"","notes":str(e)})
    return sorted(out,key=lambda r:r["path"].casefold())

class App:
    def __init__(self,root):
        self.root=root
        root.title("Cely Mod Checker")
        root.geometry("1120x720"); root.minsize(850,540)
        self.folder=tk.StringVar(); self.filter=tk.StringVar()
        self.status=tk.StringVar(value="Pronta. Scegli la cartella Mods e premi «Controlla online».")
        self.records=[]; self.results=[]
        self.build()
    def build(self):
        outer=ttk.Frame(self.root,padding=14); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text="Cely Mod Checker",font=("Segoe UI",20,"bold")).pack(anchor="w")
        ttk.Label(outer,text="Controlla i file .package e .ts4script contro una lista pubblica. Non modifica né elimina le tue mod.",wraplength=1000).pack(anchor="w",pady=(3,12))
        row=ttk.Frame(outer); row.pack(fill="x")
        ttk.Entry(row,textvariable=self.folder).pack(side="left",fill="x",expand=True)
        ttk.Button(row,text="Scegli cartella Mods",command=self.choose).pack(side="left",padx=6)
        ttk.Button(row,text="Controlla online",command=self.start).pack(side="left")
        ttk.Label(outer,text="Fonte: Sims4Life Mod Status (community indipendente, non affiliata a EA).",foreground="#5f5274").pack(anchor="w",pady=7)
        row2=ttk.Frame(outer); row2.pack(fill="x",pady=(0,6))
        ttk.Label(row2,text="Filtra:").pack(side="left")
        ttk.Entry(row2,textvariable=self.filter).pack(side="left",fill="x",expand=True,padx=8)
        self.filter.trace_add("write",lambda *_:self.populate())
        ttk.Button(row2,text="Apri pagina aggiornamento",command=self.open_update).pack(side="left",padx=(0,6))
        ttk.Button(row2,text="Esporta report CSV",command=self.export).pack(side="left")
        cols=("file","path","status","matched")
        self.tree=ttk.Treeview(outer,columns=cols,show="headings")
        for c,label,width in [("file","File",230),("path","Percorso",350),("status","Esito online",220),("matched","Voce riconosciuta",220)]:
            self.tree.heading(c,text=label); self.tree.column(c,width=width,anchor="w")
        self.tree.pack(fill="both",expand=True)
        self.tree.bind("<<TreeviewSelect>>",self.details)
        self.detail=tk.Text(outer,height=5,wrap="word",state="disabled"); self.detail.pack(fill="x",pady=(8,0))
        ttk.Label(outer,textvariable=self.status,relief="sunken",anchor="w").pack(fill="x",pady=(8,0))
    def choose(self):
        d=filedialog.askdirectory(title="Scegli la cartella Mods di The Sims 4")
        if d:self.folder.set(d)
    def start(self):
        if not Path(self.folder.get()).is_dir():
            messagebox.showwarning("Cartella Mods","Scegli prima la cartella Mods."); return
        self.status.set("Mi collego alla fonte online…")
        threading.Thread(target=self.worker,daemon=True).start()
    def worker(self):
        try:
            records=fetch_statuses(); results=scan(self.folder.get(),records)
            self.root.after(0,lambda:self.done(records,results))
        except Exception as e:
            self.root.after(0,lambda err=str(e):self.failed(err))
    def done(self,records,results):
        self.records,self.results=records,results; self.populate()
        counts={}
        for r in results: counts[r["status"]]=counts.get(r["status"],0)+1
        self.status.set(f"Online: {len(records)} voci lette. File analizzati: {len(results)}. Esiti: "+"; ".join(f"{k}: {v}" for k,v in counts.items()))
    def failed(self,e):
        self.status.set("Controllo online non riuscito.")
        messagebox.showerror("Problema con la fonte online",f"Non sono riuscita a leggere la lista online.\n{e}\n\nLa struttura della pagina potrebbe essere cambiata. Puoi aprire la fonte nel browser.")
    def populate(self):
        if not hasattr(self,"tree"): return
        self.tree.delete(*self.tree.get_children()); q=self.filter.get().casefold()
        for i,r in enumerate(self.results):
            if q and q not in " ".join(str(v) for v in r.values()).casefold(): continue
            self.tree.insert("","end",iid=str(i),values=(r["file"],r["path"],r["status"],r["matched_mod"]))
    def selected_result(self):
        sel=self.tree.selection()
        return self.results[int(sel[0])] if sel else None
    def details(self,_=None):
        r=self.selected_result()
        if not r:return
        txt=f"Stato: {r['status']}\nVoce trovata: {r['matched_mod'] or 'nessuna'}\nFonte: {r['source']}\nNote: {r['notes']}\nUltima modifica del file locale: {r['modified']}"
        self.detail.configure(state="normal"); self.detail.delete("1.0","end"); self.detail.insert("1.0",txt); self.detail.configure(state="disabled")
    def open_update(self):
        r=self.selected_result()
        if not r:
            messagebox.showinfo("Seleziona una mod","Seleziona prima una riga nella tabella.")
            return
        url=r.get("source") or SOURCE_URL
        webbrowser.open(url)
    def export(self):
        if not self.results:
            messagebox.showinfo("Nessun risultato","Esegui prima un controllo online."); return
        p=filedialog.asksaveasfilename(defaultextension=".csv",initialfile="cely_mod_report.csv",filetypes=[("CSV","*.csv")])
        if not p:return
        fields=list(self.results[0].keys())
        with open(p,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(self.results)
        self.status.set("Report salvato: "+p)

if __name__=="__main__":
    root=tk.Tk(); App(root); root.mainloop()
