"""Portfolio tab widgets. All persistence and validation belong to repository/domain."""
from datetime import date
from tkinter import messagebox
import customtkinter as ctk

from trading_gui.strategy_registry import BY_ID
from .repository import PortfolioRepository


def money(value, currency=''):
    return '—' if value is None else f'{float(value):,.2f}' + (f' {currency}' if currency else '')

class PositionDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, fields, on_save):
        super().__init__(parent)
        self.title(title)
        self.geometry('465x' + str(min(740, 140 + len(fields)*65)))
        self.resizable(False, True)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.inputs = {}
        self.grid_columnconfigure(0, weight=1)
        for index, (key, label, initial) in enumerate(fields):
            ctk.CTkLabel(self, text=label, anchor='w').grid(row=2*index,column=0,sticky='ew',padx=22,pady=(10,0))
            entry = ctk.CTkEntry(self)
            entry.insert(0, str(initial))
            entry.grid(row=2*index+1,column=0,sticky='ew',padx=22,pady=(2,0))
            self.inputs[key] = entry
        ctk.CTkButton(self,text='Save',command=lambda: self._save(on_save)).grid(
            row=len(fields)*2,column=0,sticky='ew',padx=22,pady=20)
        self.after(100,lambda: next(iter(self.inputs.values())).focus_set())

    def _save(self, callback):
        try:
            callback({key: entry.get().strip() for key,entry in self.inputs.items()})
        except (ValueError, OSError) as exc:
            messagebox.showerror('Check the information',str(exc),parent=self)
            return
        self.destroy()

class PortfolioTab(ctk.CTkFrame):
    def __init__(self,parent,repository=None):
        super().__init__(parent,fg_color='transparent')
        self.repository = repository or PortfolioRepository()
        self.show_closed = ctk.BooleanVar(value=False)
        self._build()
        self.refresh()

    def _build(self):
        self.grid_columnconfigure(0,weight=1)
        self.grid_rowconfigure(2,weight=1)
        head=ctk.CTkFrame(self,fg_color='transparent')
        head.grid(row=0,column=0,sticky='ew',pady=(6,12))
        ctk.CTkLabel(head,text='My Positions',font=ctk.CTkFont(size=21,weight='bold')).pack(side='left')
        ctk.CTkButton(head,text='+ Add Purchase',command=self.add,width=135).pack(side='right')
        bar=ctk.CTkFrame(self,fg_color='transparent')
        bar.grid(row=1,column=0,sticky='ew',pady=(0,8))
        ctk.CTkCheckBox(bar,text='Show closed trades',variable=self.show_closed,command=self.refresh).pack(side='left')
        ctk.CTkButton(bar,text='Refresh',width=85,command=self.refresh).pack(side='right')
        self.rows=ctk.CTkScrollableFrame(self,corner_radius=12)
        self.rows.grid(row=2,column=0,sticky='nsew')
        self.summary=ctk.CTkLabel(self,text='',anchor='w',text_color='gray70')
        self.summary.grid(row=3,column=0,sticky='ew',pady=(10,0))
        ctk.CTkLabel(self,text='Prices are entered manually; no live quotes or automatic stop orders. P/L excludes fees and FX.',
                     text_color='gray70',anchor='w').grid(row=4,column=0,sticky='ew',pady=(2,4))

    def refresh(self):
        for widget in self.rows.winfo_children():
            widget.destroy()
        positions=self.repository.list_positions(include_closed=self.show_closed.get())
        if not positions:
            ctk.CTkLabel(self.rows,text='No positions yet. Click “+ Add Purchase” to record your first trade.',
                         text_color='gray70').pack(pady=35)
        for p in positions:
            self._row(p)
        open_positions=[p for p in positions if p.is_open]
        totals={}
        for p in open_positions:
            if p.unrealized_pl is not None:
                totals[p.currency]=totals.get(p.currency,0)+p.unrealized_pl
        summary=', '.join(f'{currency} {money(amount)}' for currency,amount in sorted(totals.items())) or 'No manual prices entered'
        self.summary.configure(text=f'{len(open_positions)} open position(s)  |  Unrealized P/L: {summary}')

    def _row(self,p):
        card=ctk.CTkFrame(self.rows,corner_radius=9)
        card.pack(fill='x',padx=5,pady=5)
        top=ctk.CTkFrame(card,fg_color='transparent')
        top.pack(fill='x',padx=12,pady=(9,2))
        ctk.CTkLabel(top,text=f'{p.ticker}  •  {p.strategy}',font=ctk.CTkFont(size=15,weight='bold')).pack(side='left')
        ctk.CTkLabel(top,text='OPEN' if p.is_open else 'CLOSED',text_color='gray70').pack(side='right')
        current=f'Last price: {money(p.latest_price,p.currency)}' if p.is_open else f'Exit: {money(p.exit_price,p.currency)}'
        pl=p.unrealized_pl if p.is_open else p.realized_pl
        text=(f'{p.shares} shares  |  Bought {p.entry_date} @ {money(p.entry_price,p.currency)}  |  {current}\n'
              f'Initial stop: {money(p.initial_stop,p.currency)}  |  Active stop: {money(p.current_stop,p.currency)}  |  '
              f'{"Unrealized" if p.is_open else "Realized"} P/L: {money(pl,p.currency)}')
        ctk.CTkLabel(card,text=text,justify='left',anchor='w',wraplength=850).pack(fill='x',padx=12,pady=(0,6))
        actions=ctk.CTkFrame(card,fg_color='transparent')
        actions.pack(fill='x',padx=12,pady=(0,9))
        if p.is_open:
            for label,fn in [('Update Price',self.update_price),('Raise Stop',self.raise_stop),('Edit',self.edit),('Close Trade',self.close_trade)]:
                ctk.CTkButton(actions,text=label,width=100,command=lambda i=p.id,callback=fn:callback(i)).pack(side='left',padx=(0,7))
        ctk.CTkButton(actions,text='Delete',width=75,fg_color='#6b3740',command=lambda i=p.id:self.delete(i)).pack(side='right')

    def _form(self,title,fields,save):
        PositionDialog(self,title,fields,lambda values:(save(values),self.refresh()))

    def add(self):
        self._form('Record Purchase',[
            ('ticker','Ticker (e.g. AMZN or RY.TO)',''),('strategy','Strategy', BY_ID['darvas'].display_name),
            ('entry_date','Purchase date (YYYY-MM-DD)',date.today().isoformat()),
            ('shares','Shares purchased',''),('entry_price','Actual purchase price per share',''),
            ('stop','Initial protective stop',''),('currency','Currency (USD or CAD)','USD'),
            ('notes','Notes (optional)','')],lambda v:self.repository.add(**v))

    def edit(self,i):
        p=self.repository.get(i)
        self._form('Edit Purchase',[
            ('ticker','Ticker',p.ticker),('strategy','Strategy',p.strategy),('entry_date','Purchase date',p.entry_date),
            ('shares','Shares',p.shares),('entry_price','Purchase price',p.entry_price),
            ('stop','Original initial stop (fixed)',p.initial_stop),('currency','Currency',p.currency),
            ('notes','Notes',p.notes)],lambda v:self.repository.update_details(i,**v))

    def update_price(self,i):
        p=self.repository.get(i)
        self._form('Update Price — '+p.ticker,[('price','Latest observed price',p.latest_price or ''),
            ('observed_date','Price date (YYYY-MM-DD)',date.today().isoformat())],
            lambda v:self.repository.update_price(i,**v))

    def raise_stop(self,i):
        p=self.repository.get(i)
        self._form('Raise Protective Stop — '+p.ticker,[('stop','New stop (must be above current '+money(p.current_stop)+')','')],
            lambda v:self.repository.raise_stop(i,**v))

    def close_trade(self,i):
        p=self.repository.get(i)
        self._form('Close Trade — '+p.ticker,[('exit_date','Sale date (YYYY-MM-DD)',date.today().isoformat()),
            ('exit_price','Actual sale price per share','')],lambda v:self.repository.close(i,**v))

    def delete(self,i):
        p=self.repository.get(i)
        if messagebox.askyesno('Delete trade?',f'Permanently delete {p.ticker} from your journal? This cannot be undone.',parent=self):
            self.repository.delete(i)
            self.refresh()
