from app.services.cleaning import clean_records

def test_cleaning():
    rows=[{'Name':' A ','Email':' X@EXAMPLE.COM ','Phone':' +1 (555) 123-4567 '},{'Name':' A ','Email':' X@EXAMPLE.COM ','Phone':' +1 (555) 123-4567 '},{'Name':None,'Email':None,'Phone':None}]
    out,issues=clean_records(rows)
    assert len(out)==1
    assert out[0]['Name']=='A'
    assert out[0]['Email']=='x@example.com'
    assert out[0]['Phone']=='+15551234567'
    assert len(issues)==2
